from decimal import Decimal, getcontext


def calculate_pi(precision=1000):
    """
    Calculate Pi to the given number of decimal places
    using the Chudnovsky algorithm.
    """

    getcontext().prec = precision + 10  # Extra precision for accuracy

    C = 426880 * Decimal(10005).sqrt()
    M = 1
    L = 13591409
    X = 1
    K = 6
    S = Decimal(L)

    for i in range(1, precision // 14 + 1):

        M = (K**3 - 16*K) * M // (i**3)

        L += 545140134

        X *= -262537412640768000

        S += Decimal(M * L) / Decimal(X)

        K += 12

    pi = C / S

    return str(pi)



# Generate Pi with 1000 decimal places
pi_value = calculate_pi(1000)


print("Pi value:")
print(pi_value)


# Save to file
with open("pi_1000_digits.txt", "w") as file:
    file.write(pi_value)


print("\nSaved to pi_1000_digits.txt")