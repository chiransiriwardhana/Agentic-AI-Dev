(defparameter *output-file* "generated-fib.lisp")

(defparameter *generated-code*
  "(defun fib (n)
     (if (< n 2) n (+ (fib (- n 1)) (fib (- n 2)))))

   (defun print-fib (count)
     (loop for i from 0 below count
           do (format t \"~a \" (fib i)))
     (format t \"~%\"))

   (print-fib 10)")

(with-open-file (out *output-file*
                     :direction :output
                     :if-exists :supersede
                     :element-type 'character)
  (format out "~a~%" *generated-code*))

(format t "Generated ~a containing a Fibonacci printer.~%" *output-file*)