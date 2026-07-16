#include <iostream>
int main() {
    std::cout << "Enter n: ";
    int n;
    if (!(std::cin >> n) || n < 0) {
        std::cerr << "Please enter a non-negative integer." << std::endl;
        return 1;
    }
    long long a = 0, b = 1;
    for (int i = 0; i < n; ++i) {
        std::cout << a;
        if (i < n - 1) std::cout << ' ';
        long long next = a + b;
        a = b;
        b = next;
    }
    std::cout << std::endl;
    return 0;
}
