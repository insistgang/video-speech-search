import sys
import os

print("Python executable:", sys.executable)
print("Working directory:", os.getcwd())
print("API_KEY:", repr(os.getenv("API_KEY")))
print("\nsys.path:")
for p in sys.path:
    print("  ", p)
