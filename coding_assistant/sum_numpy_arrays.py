#!/usr/bin/env python3
"""
Demonstrates summing two NumPy arrays.
"""

import numpy as np
import jax.numpy as jnp

def main() -> None:
    # Define two example arrays
    a = np.array(["1", 2, 3])
    b = np.array([4, 5, 6])
    
    # Compute element-wise sum
    c = a + b
    
    print("Array a:", a)
    print("Array b:", b)
    print("sum (a + b):", c)


if __name__ == "__main__":
    main()
