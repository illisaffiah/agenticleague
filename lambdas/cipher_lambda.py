import json


def lambda_handler(event, context):
    """
    Cipher/encoding tool for door puzzles and code transformations.
    
    Actions:
      - reverse: Reverse the string ("open" → "nepo")
      - letter_to_number: Each letter → alphabet position concatenated ("fghi" → "6789")
      - letter_to_number_padded: Each letter → 2-digit zero-padded position ("open" → "15160514")
      - number_to_letter: Each number → letter ("6789" → "fghi")
      - caesar: Caesar cipher shift (params: text, shift)
      - rot13: ROT13 cipher
      - atbash: Atbash cipher (a↔z, b↔y)
      - ascii/to_ascii: Characters → ASCII codes
      - binary/to_binary: Characters → binary
      - hex/to_hex: Characters → hex
      - morse/to_morse: Text → morse code
      - base64_encode: Base64 encode
      - base64_decode: Base64 decode
      - upper/lower/swap_case: Case transformations
      - word_reverse: Reverse word order
    """
    params = event
    if 'parameters' in event and isinstance(event['parameters'], list):
        params = {}
        for p in event['parameters']:
            params[p.get('name', '')] = p.get('value', '')
    elif 'body' in event:
        params = json.loads(event['body']) if isinstance(event['body'], str) else event['body']
    elif 'input' in event and isinstance(event['input'], dict):
        params = event['input']

    text = str(params.get('text', '') or params.get('code', '') or params.get('input', '') or '')
    action = str(params.get('action', '') or params.get('operation', '') or params.get('method', '') or 'reverse')
    shift = int(params.get('shift', 0) or 0)

    try:
        result = apply_cipher(text, action, shift)
        return {"result": result, "success": True}
    except Exception as e:
        return {"result": "", "success": False, "error": str(e)}


def apply_cipher(text, action, shift=0):
    import re
    action = action.lower().strip().replace(' ', '_').replace('-', '_')

    # === STRING MANIPULATION ===

    if action == 'reverse':
        return text[::-1]

    if action == 'word_reverse':
        return ' '.join(text.split()[::-1])

    if action in ('upper', 'uppercase'):
        return text.upper()

    if action in ('lower', 'lowercase'):
        return text.lower()

    if action == 'swap_case':
        return text.swapcase()

    if action == 'remove_spaces':
        return text.replace(' ', '')

    # === LETTER ↔ NUMBER CONVERSIONS ===

    if action in ('letter_to_number', 'letters_to_numbers', 'l2n', 'alpha_to_num'):
        # "fghi" → "6789", "open" → "1516514"
        result = ''
        for ch in text.lower():
            if ch.isalpha():
                result += str(ord(ch) - ord('a') + 1)
        return result

    if action in ('letter_to_number_padded', 'l2n_padded', 'padded'):
        # "fghi" → "06070809", "open" → "15160514", "nepo" → "14051615"
        result = ''
        for ch in text.lower():
            if ch.isalpha():
                result += f'{ord(ch) - ord("a") + 1:02d}'
        return result

    if action in ('number_to_letter', 'numbers_to_letters', 'n2l', 'num_to_alpha'):
        # If numbers are space/comma separated, use those as delimiters
        if any(sep in text for sep in [' ', ',', '-', '.']):
            nums = re.findall(r'\d+', text)
            return ''.join(chr(ord('a') + int(n) - 1) for n in nums if 1 <= int(n) <= 26)
        # Otherwise try single digits first
        digits = ''.join(c for c in text if c.isdigit())
        result = ''
        for d in digits:
            n = int(d)
            if 1 <= n <= 9:
                result += chr(ord('a') + n - 1)
        return result

    # === CLASSIC CIPHERS ===

    if action in ('caesar', 'caesar_cipher', 'shift'):
        result = ''
        for ch in text:
            if ch.isalpha():
                base = ord('A') if ch.isupper() else ord('a')
                result += chr((ord(ch) - base + shift) % 26 + base)
            else:
                result += ch
        return result

    if action == 'rot13':
        result = ''
        for ch in text:
            if ch.isalpha():
                base = ord('A') if ch.isupper() else ord('a')
                result += chr((ord(ch) - base + 13) % 26 + base)
            else:
                result += ch
        return result

    if action == 'atbash':
        result = ''
        for ch in text:
            if ch.isalpha():
                if ch.isupper():
                    result += chr(ord('Z') - (ord(ch) - ord('A')))
                else:
                    result += chr(ord('z') - (ord(ch) - ord('a')))
            else:
                result += ch
        return result

    # === ENCODING FORMATS ===

    if action in ('ascii', 'to_ascii'):
        return ' '.join(str(ord(c)) for c in text)

    if action in ('from_ascii', 'ascii_to_text'):
        nums = [int(n) for n in text.split() if n.isdigit()]
        return ''.join(chr(n) for n in nums)

    if action in ('binary', 'to_binary'):
        return ' '.join(format(ord(c), '08b') for c in text)

    if action in ('from_binary', 'binary_to_text'):
        return ''.join(chr(int(b, 2)) for b in text.split())

    if action in ('hex', 'to_hex'):
        return ' '.join(format(ord(c), '02x') for c in text)

    if action in ('from_hex', 'hex_to_text'):
        hex_str = text.replace(' ', '')
        return bytes.fromhex(hex_str).decode('utf-8')

    if action in ('base64_encode', 'base64', 'b64_encode'):
        import base64
        return base64.b64encode(text.encode()).decode()

    if action in ('base64_decode', 'b64_decode'):
        import base64
        return base64.b64decode(text.encode()).decode()

    # === MORSE CODE ===

    if action in ('morse', 'to_morse'):
        morse_map = {
            'a': '.-', 'b': '-...', 'c': '-.-.', 'd': '-..', 'e': '.',
            'f': '..-.', 'g': '--.', 'h': '....', 'i': '..', 'j': '.---',
            'k': '-.-', 'l': '.-..', 'm': '--', 'n': '-.', 'o': '---',
            'p': '.--.', 'q': '--.-', 'r': '.-.', 's': '...', 't': '-',
            'u': '..-', 'v': '...-', 'w': '.--', 'x': '-..-', 'y': '-.--',
            'z': '--..', ' ': '/'
        }
        return ' '.join(morse_map.get(c.lower(), c) for c in text)

    if action in ('from_morse', 'morse_to_text'):
        morse_to_char = {
            '.-': 'a', '-...': 'b', '-.-.': 'c', '-..': 'd', '.': 'e',
            '..-.': 'f', '--.': 'g', '....': 'h', '..': 'i', '.---': 'j',
            '-.-': 'k', '.-..': 'l', '--': 'm', '-.': 'n', '---': 'o',
            '.--.': 'p', '--.-': 'q', '.-.': 'r', '...': 's', '-': 't',
            '..-': 'u', '...-': 'v', '.--': 'w', '-..-': 'x', '-.--': 'y',
            '--..': 'z', '/': ' '
        }
        words = text.split(' / ') if ' / ' in text else [text]
        result = ''
        for word in words:
            for code in word.split():
                result += morse_to_char.get(code, '?')
            result += ' '
        return result.strip()

    # Default: return as-is
    return text


# Test
if __name__ == "__main__":
    print("=== DOOR PUZZLE TESTS ===")
    print(f"reverse('open') = '{apply_cipher('open', 'reverse')}'")
    print(f"letter_to_number('fghi') = '{apply_cipher('fghi', 'letter_to_number')}'")
    print(f"letter_to_number('open') = '{apply_cipher('open', 'letter_to_number')}'")
    print(f"letter_to_number('nepo') = '{apply_cipher('nepo', 'letter_to_number')}'")
    print(f"letter_to_number_padded('fghi') = '{apply_cipher('fghi', 'letter_to_number_padded')}'")
    print(f"letter_to_number_padded('open') = '{apply_cipher('open', 'letter_to_number_padded')}'")
    print(f"letter_to_number_padded('nepo') = '{apply_cipher('nepo', 'letter_to_number_padded')}'")
    print()
    print("=== OTHER CIPHERS ===")
    print(f"caesar('hello', shift=3) = '{apply_cipher('hello', 'caesar', 3)}'")
    print(f"rot13('hello') = '{apply_cipher('hello', 'rot13')}'")
    print(f"atbash('open') = '{apply_cipher('open', 'atbash')}'")
