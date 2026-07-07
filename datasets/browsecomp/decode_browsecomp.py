#!/usr/bin/env python3
"""
Decode browse_comp_test_set.csv using canary-based decryption and save to JSONL format
Based on the decryption code from BrowseCompEval
"""

import csv
import json
import base64
import hashlib
import os

def derive_key(password: str, length: int) -> bytes:
    """Derive a fixed-length key from the password using SHA256."""
    hasher = hashlib.sha256()
    hasher.update(password.encode())
    key = hasher.digest()
    return key * (length // len(key)) + key[: length % len(key)]

def decrypt(ciphertext_b64: str, password: str) -> str:
    """Decrypt base64-encoded ciphertext with XOR."""
    if not ciphertext_b64 or not password:
        return ciphertext_b64

    try:
        encrypted = base64.b64decode(ciphertext_b64)
        key = derive_key(password, len(encrypted))
        decrypted = bytes(a ^ b for a, b in zip(encrypted, key))
        return decrypted.decode('utf-8')
    except Exception as e:
        print(f"Error decrypting: {e}")
        return ciphertext_b64

def process_csv_to_jsonl(input_file, output_file):
    """Process CSV file and save decrypted data to JSONL"""

    if not os.path.exists(input_file):
        print(f"Input file {input_file} does not exist")
        return False

    try:
        with open(input_file, 'r', encoding='utf-8') as csvfile, \
             open(output_file, 'w', encoding='utf-8') as jsonlfile:

            reader = csv.DictReader(csvfile)

            count = 0
            for row in reader:
                # Get the canary value for decryption
                canary = row.get('canary', '')
                if not canary and 'canary' in row:
                    canary = row['canary']

                # Decrypt the problem and answer fields using canary as key
                decrypted_row = {
                    'problem': decrypt(row['problem'], canary),
                    'answer': decrypt(row['answer'], canary),
                    'problem_topic': row['problem_topic'],
                    'canary': row['canary']
                }

                # Write to JSONL (one JSON object per line)
                json.dump(decrypted_row, jsonlfile, ensure_ascii=False, indent=None)
                jsonlfile.write('\n')
                count += 1

            print(f"Successfully processed {count} records")
            print(f"Output saved to: {output_file}")
            return True

    except Exception as e:
        print(f"Error processing file: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    import os
    here = os.path.dirname(os.path.abspath(__file__))
    input_csv = os.path.join(here, "browse_comp_test_set.csv")
    output_jsonl = os.path.join(here, "browse_comp_test_set_decrypted.jsonl")

    print(f"Processing {input_csv}")
    print("Using canary-based XOR decryption method")
    print("=" * 50)

    success = process_csv_to_jsonl(input_csv, output_jsonl)

    if success:
        print("\nProcessing completed successfully!")

        # Show first few decoded entries
        print("\nFirst 2 decrypted entries:")
        try:
            with open(output_jsonl, 'r', encoding='utf-8') as f:
                for i, line in enumerate(f):
                    if i >= 2:
                        break
                    data = json.loads(line)
                    print(f"Entry {i+1}:")
                    print(f"  Problem: {data['problem'][:200]}{'...' if len(data['problem']) > 200 else ''}")
                    print(f"  Answer: {data['answer']}")
                    print(f"  Topic: {data['problem_topic']}")
                    print()
        except Exception as e:
            print(f"Error showing preview: {e}")

if __name__ == "__main__":
    main()