from websearch_lambda import extract_answer

CASES = [
    # (label, page_text, question, expected)
    ("hyperpod 40%",
     "SageMaker HyperPod can reduce model training time by up to 40% with resiliency.",
     "what feature can reduce training time by up to 40%?", "HyperPod"),
    ("bedrock 200 largest",
     "New customers get $100 at sign-up and can earn up to $100 more, for up to $200 in credits.",
     "up to how many credits can a new customer receive free?", "$200"),
    ("money single",
     "Try it free with $300 in promotional credits for new accounts.",
     "how much in credits?", "$300"),
    ("percent feature reorder",
     "With built-in resiliency, Trainium accelerates jobs and cuts training time by 50%.",
     "what reduces training time by 50%?", "Trainium"),
    ("no answer avail (fallback None)",
     "This page is about general cloud computing concepts and best practices.",
     "what feature reduces training time by 40%?", None),
    ("money with commas",
     "Enterprise customers may receive up to $1,000 in onboarding credits.",
     "how many dollars in credits?", "$1,000"),
    # THE REAL $300 TRAP: page has a bigger unrelated figure; answer must be the
    # credits figure ($200), NOT the global max ($300 EC2 example).
    ("bedrock 200 not 300 trap",
     "Amazon EC2 instances can cost up to $300 per month for large workloads. "
     "New AWS customers can get started with up to $200 in free credits to explore AWS AI.",
     "up to how many credits can a new AWS customer receive to try AWS AI for free?", "$200"),
    # another distractor: pricing table with big numbers, credits stated separately
    ("credits vs pricing distractor",
     "Reserved instances are available for $500 upfront. "
     "The AWS Free Tier gives new customers up to $200 in credits.",
     "how many credits for new customers free?", "$200"),
]

ok = True
for label, text, q, expected in CASES:
    got = extract_answer(text, q)
    status = "OK" if got == expected else f"FAIL (got {got!r}, want {expected!r})"
    if got != expected:
        ok = False
    print(f"[{status:6}] {label:26} -> {got!r}")
print("-"*60)
print("ALL EXTRACTION CASES PASS" if ok else ">>> some cases need tuning <<<")
