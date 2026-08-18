# test_worker.py
# Dummy file for testing manual worker run.

def greet_user(name):
    """Returns a greeting message for the user."""
    return f"Hello, {name}!"

def main():
    print("Test Worker Running")
    print(greet_user("Developer"))

if __name__ == "__main__":
    main()
