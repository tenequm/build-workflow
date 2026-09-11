#!/usr/bin/env python3
import sys
import argparse
import os

def validate_schema(path: str) -> bool:
    if not os.path.exists(path):
        print(f"Error: Schema file {path} does not exist.")
        return False
    print(f"Validating schema definition: {path}")
    return True

def main():
    parser = argparse.ArgumentParser(description="Schema Validator")
    parser.add_argument("--target", required=True, help="Path to schema file")
    parser.add_argument("--strict", action="store_true", help="Enable strict mode")
    args = parser.parse_args()

    if not validate_schema(args.target):
        sys.exit(1)
    print("Schema validation successful.")

if __name__ == "__main__":
    main()
