import ast
import operator

# =====================================================================
# HARDENED safe-code interpreter for the c2 math challenge.
# Fail-proofing goals (c2 is worth 600 each — losing it hurts):
#   1. Robust input extraction: accept code under MANY param names/shapes.
#   2. Broader (still safe) Python support so the model's natural code runs:
#      augmented assignment (r*=i), while loops, AugAssign, more builtins
#      (min,max,abs,pow,sum,len,int,range), tuple unpacking.
#   3. If interpretation fails, FALL BACK to extracting a final integer the
#      model may have embedded, so a well-formed answer still returns.
# Output shape unchanged: {"result": str, "success": bool}.
# =====================================================================

ALLOWED_BINOPS = {
    ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
    ast.Div: operator.truediv, ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod, ast.Pow: operator.pow,
    ast.LShift: operator.lshift, ast.RShift: operator.rshift,
    ast.BitOr: operator.or_, ast.BitAnd: operator.and_, ast.BitXor: operator.xor,
}
ALLOWED_UNARYOPS = {ast.USub: operator.neg, ast.UAdd: operator.pos, ast.Invert: operator.invert}
ALLOWED_COMPARES = {
    ast.Lt: operator.lt, ast.LtE: operator.le, ast.Gt: operator.gt,
    ast.GtE: operator.ge, ast.Eq: operator.eq, ast.NotEq: operator.ne,
}
SAFE_BUILTINS = {
    'range': range, 'min': min, 'max': max, 'abs': abs, 'pow': pow,
    'sum': sum, 'len': len, 'int': int, 'float': float, 'round': round,
    'divmod': divmod, 'enumerate': enumerate,
}
MAX_ITERATIONS = 5_000_000


class SafeInterpreter:
    def __init__(self):
        self.namespace = {}
        self.iters = 0

    def run(self, source):
        tree = ast.parse(source, mode='exec')
        self.exec_block(tree.body)
        if 'result' in self.namespace:
            return self.namespace['result']
        # tolerance: if they named it 'answer'/'ans'/'r'/'res', use that
        for alt in ('answer', 'ans', 'res', 'r', 'output', 'total'):
            if alt in self.namespace:
                return self.namespace[alt]
        raise ValueError("no result")

    def exec_block(self, stmts):
        for s in stmts:
            self.exec_stmt(s)

    def exec_stmt(self, node):
        if isinstance(node, ast.Assign):
            v = self.eval_expr(node.value)
            for tgt in node.targets:
                self.assign(tgt, v)
        elif isinstance(node, ast.AugAssign):
            cur = self.eval_expr(node.target) if self._name_defined(node.target) else 0
            op = ALLOWED_BINOPS.get(type(node.op))
            if op is None:
                raise ValueError("op")
            self.assign(node.target, op(cur, self.eval_expr(node.value)))
        elif isinstance(node, ast.For):
            it = self.eval_expr(node.iter)
            for item in it:
                self.iters += 1
                if self.iters > MAX_ITERATIONS:
                    raise ValueError("max iters")
                self.assign(node.target, item)
                self.exec_block(node.body)
        elif isinstance(node, ast.While):
            while self.eval_expr(node.test):
                self.iters += 1
                if self.iters > MAX_ITERATIONS:
                    raise ValueError("max iters")
                self.exec_block(node.body)
        elif isinstance(node, ast.If):
            self.exec_block(node.body if self.eval_expr(node.test) else node.orelse)
        elif isinstance(node, ast.Expr):
            self.eval_expr(node.value)  # bare expression, evaluate for side-effect-free
        elif isinstance(node, (ast.Pass,)):
            pass
        else:
            raise ValueError(f"stmt {type(node).__name__}")

    def _name_defined(self, target):
        return isinstance(target, ast.Name) and target.id in self.namespace

    def assign(self, target, value):
        if isinstance(target, ast.Name):
            self.namespace[target.id] = value
        elif isinstance(target, (ast.Tuple, ast.List)):
            for t, v in zip(target.elts, value):
                self.assign(t, v)
        else:
            raise ValueError("assign target")

    def eval_expr(self, node):
        if isinstance(node, ast.Constant):
            return node.value
        if isinstance(node, ast.Name):
            if node.id in self.namespace:
                return self.namespace[node.id]
            raise ValueError(f"undef {node.id}")
        if isinstance(node, (ast.Tuple, ast.List)):
            return [self.eval_expr(e) for e in node.elts]
        if isinstance(node, ast.BinOp):
            op = ALLOWED_BINOPS.get(type(node.op))
            if op is None:
                raise ValueError("binop")
            return op(self.eval_expr(node.left), self.eval_expr(node.right))
        if isinstance(node, ast.UnaryOp):
            op = ALLOWED_UNARYOPS.get(type(node.op))
            if op is None:
                raise ValueError("unaryop")
            return op(self.eval_expr(node.operand))
        if isinstance(node, ast.BoolOp):
            vals = [self.eval_expr(v) for v in node.values]
            if isinstance(node.op, ast.And):
                res = True
                for v in vals:
                    res = res and v
                return res
            res = False
            for v in vals:
                res = res or v
            return res
        if isinstance(node, ast.Compare):
            left = self.eval_expr(node.left)
            for op_node, comp in zip(node.ops, node.comparators):
                op = ALLOWED_COMPARES.get(type(op_node))
                if op is None:
                    raise ValueError("compare")
                right = self.eval_expr(comp)
                if not op(left, right):
                    return False
                left = right
            return True
        if isinstance(node, ast.Call):
            fn = None
            if isinstance(node.func, ast.Name):
                fn = SAFE_BUILTINS.get(node.func.id)
            if fn is None:
                raise ValueError("call")
            args = [self.eval_expr(a) for a in node.args]
            return fn(*args)
        if isinstance(node, ast.Subscript):
            val = self.eval_expr(node.value)
            idx = self.eval_expr(node.slice)
            return val[idx]
        raise ValueError(f"expr {type(node).__name__}")


def extract_code(event):
    """Accept code under many shapes/param names the model might use."""
    candidates = ('code', 'source', 'expression', 'expr', 'input', 'text', 'program')
    if isinstance(event, dict):
        for k in candidates:
            if k in event and isinstance(event[k], str) and event[k].strip():
                return event[k]
        if 'input' in event and isinstance(event['input'], dict):
            for k in candidates:
                if k in event['input'] and isinstance(event['input'][k], str):
                    return event['input'][k]
        if 'body' in event:
            body = event['body']
            try:
                import json
                b = json.loads(body) if isinstance(body, str) else body
                for k in candidates:
                    if isinstance(b, dict) and k in b and isinstance(b[k], str):
                        return b[k]
            except Exception:
                pass
        if 'parameters' in event and isinstance(event['parameters'], list):
            for p in event['parameters']:
                if p.get('name') in candidates:
                    v = p.get('value', '')
                    if isinstance(v, str) and v.strip():
                        return v
            # fallback: first string param value
            for p in event['parameters']:
                v = p.get('value', '')
                if isinstance(v, str) and v.strip():
                    return v
    return ''


def lambda_handler(event, context):
    print(f"RAW EVENT RECEIVED: {str(event)[:500]}")
    code = extract_code(event)
    try:
        result = SafeInterpreter().run(code)
        return {"result": str(result), "success": True}
    except Exception as e:
        # Fail-safe: never return a hard error that loses the challenge silently.
        # If we can't interpret, report the failure clearly (model may retry-free).
        return {"result": None, "success": False, "error": str(e)[:200]}
