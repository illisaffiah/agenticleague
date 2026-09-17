import ast
import operator

ALLOWED_BINOPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
ALLOWED_UNARYOPS = {
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}
ALLOWED_COMPARES = {
    ast.Lt: operator.lt,
    ast.LtE: operator.le,
    ast.Gt: operator.gt,
    ast.GtE: operator.ge,
    ast.Eq: operator.eq,
    ast.NotEq: operator.ne,
}

MAX_ITERATIONS = 100000

class SafeInterpreter:
    def __init__(self):
        self.namespace = {}
        self.iterations_used = 0

    def run(self, source):
        tree = ast.parse(source, mode='exec')
        self.exec_block(tree.body)
        if 'result' not in self.namespace:
            raise ValueError("Code must assign a final value to a variable named 'result'")
        return self.namespace['result']

    def exec_block(self, stmts):
        for stmt in stmts:
            self.exec_stmt(stmt)

    def exec_stmt(self, node):
        if isinstance(node, ast.Assign):
            value = self.eval_expr(node.value)
            self.assign(node.targets[0], value)
        elif isinstance(node, ast.For):
            iter_val = self.eval_expr(node.iter)
            for item in iter_val:
                self.iterations_used += 1
                if self.iterations_used > MAX_ITERATIONS:
                    raise ValueError(f"Exceeded max iterations ({MAX_ITERATIONS})")
                self.assign(node.target, item)
                self.exec_block(node.body)
        elif isinstance(node, ast.If):
            test = self.eval_expr(node.test)
            self.exec_block(node.body if test else node.orelse)
        else:
            raise ValueError(f"Statement type {type(node).__name__} not allowed")

    def assign(self, target, value):
        if isinstance(target, ast.Name):
            self.namespace[target.id] = value
        elif isinstance(target, ast.Tuple):
            for t, v in zip(target.elts, value):
                self.assign(t, v)
        else:
            raise ValueError(f"Assignment target {type(target).__name__} not allowed")

    def eval_expr(self, node):
        if isinstance(node, ast.Constant):
            return node.value
        if isinstance(node, ast.Name):
            if node.id not in self.namespace:
                raise ValueError(f"Undefined variable: {node.id}")
            return self.namespace[node.id]
        if isinstance(node, ast.Tuple):
            return tuple(self.eval_expr(e) for e in node.elts)
        if isinstance(node, ast.BinOp):
            op = ALLOWED_BINOPS.get(type(node.op))
            if op is None:
                raise ValueError(f"Operator {type(node.op).__name__} not allowed")
            return op(self.eval_expr(node.left), self.eval_expr(node.right))
        if isinstance(node, ast.UnaryOp):
            op = ALLOWED_UNARYOPS.get(type(node.op))
            if op is None:
                raise ValueError(f"Operator {type(node.op).__name__} not allowed")
            return op(self.eval_expr(node.operand))
        if isinstance(node, ast.Compare):
            left = self.eval_expr(node.left)
            for op_node, comparator in zip(node.ops, node.comparators):
                op = ALLOWED_COMPARES.get(type(op_node))
                if op is None:
                    raise ValueError(f"Comparison {type(op_node).__name__} not allowed")
                right = self.eval_expr(comparator)
                if not op(left, right):
                    return False
                left = right
            return True
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id == 'range':
                args = [self.eval_expr(a) for a in node.args]
                return range(*args)
            raise ValueError("Only range() calls are allowed")
        raise ValueError(f"Expression type {type(node).__name__} not allowed")


def extract_code(event):
    if 'code' in event:
        return event['code']
    if 'input' in event and isinstance(event['input'], dict) and 'code' in event['input']:
        return event['input']['code']
    if 'parameters' in event and isinstance(event['parameters'], list):
        for param in event['parameters']:
            if param.get('name') == 'code':
                return param.get('value', '')
    return ''


def lambda_handler(event, context):
    print(f"RAW EVENT RECEIVED: {event}")
    code = extract_code(event)
    try:
        interpreter = SafeInterpreter()
        result = interpreter.run(code)
        return {"result": str(result), "success": True}
    except Exception as e:
        return {"result": None, "success": False, "error": str(e)}
