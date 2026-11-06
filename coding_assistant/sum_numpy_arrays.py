#!/usr/bin/env python3
"""
Demonstrates summing two NumPy arrays and two JAX arrays.
"""

import numpy as np
import jax
import jax.numpy as jnp

def main() -> None:
    # Define two example NumPy arrays
    a_np = np.array([1, 2, 3])
    b_np = np.array([4, 5, 6])
    c_np = a_np + b_np
    print("NumPy Array a:", a_np)
    print("NumPy Array b:", b_np)
    print("NumPy Array Sum:", c_np)

    # Define two example JAX arrays
    a_jax = jnp.array([1, 2, 3])
    b_jax = jnp.array([4, 5, 6])
    c_jax = a_jax + b_jax
    print("\nJAX Array a:", a_jax)
    print("JAX Array b:", b_jax)
    print("JAX Array Sum:", c_jax)

    # Print some elements of the JAX arrays
    print("\nSome elements of JAX Array a:", a_jax[:2])
    print("Some elements of JAX Array b:", b_jax[1:])

if __name__ == "__main__":
    main()
