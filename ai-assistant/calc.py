OPS = {
    "+": lambda a, b: a + b,
    "-": lambda a, b: a - b,
    "*": lambda a, b: a * b,
    "/": lambda a, b: a / b,
}
def calculate(a: float, operator: str, b: float) -> float:
    if operator not in OPS:
        raise ValueError(f"Unknown operator: {operator!r}. Use one of {list(OPS)}")
    if operator == "/" and b == 0:
        raise ZeroDivisionError("Cannot divide by zero")
    return OPS[operator](a, b)
def run_once() -> None:
    line = input("Expression (e.g. 3 + 4), or 'q' to quit: ").strip()
    if not line or line.lower() == "q":
        raise EOFError
    parts = line.split()
    if len(parts) != 3:
        print("Format: <number> <operator> <number>  —  example: 10 / 2")
        return
    left_s, op, right_s = parts
    a, b = float(left_s), float(right_s)
    result = calculate(a, op, b)
    print(result)
def main() -> None:
    print("Simple calculator. Operators: +  -  *  /")
    while True:
        try:
            run_once()
        except EOFError:
            break
        except ValueError as e:
            print(f"Error: {e}")
        except ZeroDivisionError as e:
            print(f"Error: {e}")
if __name__ == "__main__":
    main()
