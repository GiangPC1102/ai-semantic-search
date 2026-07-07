#!/usr/bin/env python3
"""Generate Python gRPC code from proto files."""

import subprocess
import sys
from pathlib import Path


def generate_grpc_code():
    project_root = Path(__file__).parent.parent
    proto_dir = project_root / "proto"
    output_dir = project_root / "grpc_generated"

    output_dir.mkdir(exist_ok=True)

    proto_files = list(proto_dir.glob("*.proto"))

    if not proto_files:
        print("No .proto files found in the proto directory")
        return False

    print(f"Found {len(proto_files)} proto file(s)")

    for proto_file in proto_files:
        print(f"Generating gRPC code for {proto_file.name}...")

        cmd = [
            sys.executable,
            "-m",
            "grpc_tools.protoc",
            f"--proto_path={proto_dir}",
            f"--python_out={output_dir}",
            f"--grpc_python_out={output_dir}",
            str(proto_file),
        ]

        try:
            subprocess.run(cmd, check=True, capture_output=True, text=True)
            print(f"✓ Successfully generated gRPC code for {proto_file.name}")
        except subprocess.CalledProcessError as e:
            print(f"✗ Error generating gRPC code for {proto_file.name}:")
            print(f"  Command: {' '.join(cmd)}")
            print(f"  Error: {e.stderr}")
            return False

    init_file = output_dir / "__init__.py"
    if not init_file.exists():
        init_file.write_text("# Generated gRPC code\n")

    print("✓ All gRPC code generated successfully!")
    print(f"Generated files are in: {output_dir}")

    return True


if __name__ == "__main__":
    success = generate_grpc_code()
    sys.exit(0 if success else 1)
