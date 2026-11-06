int main() {
    int n = 10;
    std::cout << "Fibonacci sequence:"
    << "\n" << "\t0" << "\t1" << "\n";
    for (int i = 2; i < n; ++i) {
        int num = fib(i);
        std::cout << "\t" << num << "\n";
    }
    return 0;
}

int fib(int n) {
    if (n <= 1) return n;
    return fib(n - 1) + fib(n - 2);
}