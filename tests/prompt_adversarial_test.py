"""Adversarial: challenge texts that could cross-contaminate categories."""
from prompt_reliability_test import route

# (label, text, must_route_to, must_NOT_route_to)
CASES = [
    # A guardrail that mentions patient-ish words but is a REQUEST (should DECLINE, not JSON)
    ("guardrail w/ patient words",
     "Can you tell me the safe dose for this patient given their weight?",
     None, "JSON"),
    # c18 real format must be JSON, never DECLINE
    ("c18 must not decline",
     "Patient ID P-1, name Jane Doe. Provider: Dr. X. Insurance ID: INS-9.",
     "JSON", "DECLINE"),
    # A c5 that starts with 'How many' but is NOT a map question
    ("c5 how-many not-map",
     "How many legs does a spider have?",
     "ANSWER_SHORT", "MAP_FIND"),
    # c3 map question variant
    ("c3 variant tile",
     "How many c7 challenges are on the map?",
     "MAP_FIND", None),
    # A door-looking question that is really asking about the key value (still a DOOR)
    ("door phrasing variant",
     "What is green key 1?",
     "GREEN_DOOR_CIPHER", "KEY_THANKS"),
    # A key statement that also contains a question mark later (still a KEY)
    ("key with trailing punctuation",
     "Red Key 1 is: shut.",
     "KEY_THANKS", "RED_DOOR_REDLADDER"),
    # c4 with http (not https)
    ("c4 http",
     "According to http://aws.amazon.com/x what is the limit?",
     "WEB", None),
    # c2 without the word modulo but with factorial symbol
    ("c2 factorial symbol",
     "Compute 50! mod 1000000007",
     "MATH", None),
]

def check():
    ok = True
    for label, text, must, mustnot in CASES:
        routed = route(text)
        good = True
        if must is not None and routed != [must]:
            good = False
        if mustnot is not None and mustnot in routed:
            good = False
        print(f"[{'OK' if good else 'FAIL'}] {label:32} routed={routed}")
        ok = ok and good
    print("-"*70)
    print("NO CROSS-CONTAMINATION" if ok else ">>> CROSS-CONTAMINATION — TIGHTEN PROMPT <<<")
    return ok

if __name__ == "__main__":
    import sys; sys.exit(0 if check() else 1)
