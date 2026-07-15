#include <iostream>
int main() {
    const int n = 10;
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
