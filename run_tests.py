from pathlib import Path
import py_compile


def main():
    for path in sorted(Path(".").glob("*.py")):
        py_compile.compile(str(path), doraise=True)
        print(f"Compiled {path}")
    print("All Python files compile.")


if __name__ == "__main__":
    main()
