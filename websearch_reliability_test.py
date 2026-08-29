"""Full websearch reliability check: handler across all invocation shapes + edge cases."""
import websearch_lambda as w

# Real page snippets (from your actual direct-invoke outputs)
SM = ("Amazon SageMaker AI is a fully managed service. SageMaker AI accelerates your AI journey "
      "with capabilities like model customization, HyperPod which reduces training time by up to 40% "
      "with automated cluster management, and inference optimization.")
BD = ("Try AWS AI for Free. New AWS customers receive up to $200 in AWS credits to try AWS AI for free. "
      "Get started for free.")
BD_TRAP = ("Amazon EC2 can cost up to $300 per month for large workloads. "
           "New AWS customers receive up to $200 in AWS credits to try AWS AI for free.")

def run(label, event, page, expect_answer):
    w.fetch_url = lambda url, keywords=None, _p=page: _p  # stub network
    r = w.lambda_handler(event, None)
    # meaningful checks: the 'answer' field is correct AND content carries it
    ans = r.get('answer')
    content = r.get('content') or ''
    # content now = "ANSWER: X\n\n<grounding page text>" — check answer field + hint present
    ok = (ans == expect_answer) and content.startswith(f"ANSWER: {expect_answer}")
    print(f"[{'OK' if ok else 'FAIL'}] {label}")
    if not ok:
        print(f"      got answer={ans!r} content={content!r}  expected={expect_answer!r}")
    return ok

allok = True

# --- Shape 1: AgentCore 'parameters' list (what the gateway sends) ---
allok &= run("params-shape, sagemaker, question present",
    {'parameters':[{'name':'url','value':'https://x'},
                   {'name':'keywords','value':'training time,40%,reduce'},
                   {'name':'question','value':'what feature can reduce training time by up to 40%?'}]},
    SM, 'HyperPod')

allok &= run("params-shape, bedrock, question present",
    {'parameters':[{'name':'url','value':'http://x'},
                   {'name':'keywords','value':'credits,free,new customer'},
                   {'name':'question','value':'up to how many credits for a new AWS customer free?'}]},
    BD, '$200')

# --- Shape 2: gateway DROPS question (the real bug we fixed) ---
allok &= run("params-shape, bedrock, NO question (keywords only)",
    {'parameters':[{'name':'url','value':'http://x'},
                   {'name':'keywords','value':'credits,free,new customer'}]},
    BD, '$200')

allok &= run("params-shape, sagemaker, NO question (keywords only)",
    {'parameters':[{'name':'url','value':'https://x'},
                   {'name':'keywords','value':'training time,40%,reduce'}]},
    SM, 'HyperPod')

# --- Shape 3: gateway drops BOTH question and keywords (worst case) ---
allok &= run("params-shape, bedrock, NO question NO keywords",
    {'parameters':[{'name':'url','value':'http://x'}]},
    BD, '$200')

# --- Shape 4: the $300 trap with question dropped ---
allok &= run("bedrock $300-trap, NO question",
    {'parameters':[{'name':'url','value':'http://x'},
                   {'name':'keywords','value':'credits,free'}]},
    BD_TRAP, '$200')

# --- Shape 5: direct body dict ---
allok &= run("body-dict shape",
    {'url':'http://x','keywords':'credits,free','question':'how many credits free?'},
    BD, '$200')

# --- Shape 6: page has NO extractable answer -> content = raw page (graceful) ---
w.fetch_url = lambda url, keywords=None: "This page is about general cloud concepts."
r = w.lambda_handler({'parameters':[{'name':'url','value':'http://x'},{'name':'keywords','value':'training,40%'}]}, None)
graceful = (r.get('content') == "This page is about general cloud concepts." and 'suggested_answer' not in r)
print(f"[{'OK' if graceful else 'FAIL'}] no-answer page -> returns raw content, no suggested_answer (graceful degrade)")
allok &= graceful

# --- Shape 7: missing URL -> clean error, no crash ---
r = w.lambda_handler({'parameters':[{'name':'keywords','value':'x'}]}, None)
noerr = (r.get('success') is False and 'error' in r)
print(f"[{'OK' if noerr else 'FAIL'}] missing url -> success:false with error (no crash)")
allok &= noerr

print("-"*60)
print("WEBSEARCH RELIABILITY: ALL PASS" if allok else ">>> FAILURES ABOVE <<<")
