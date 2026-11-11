from tkinter import *

# Create the main window
window = Tk()
window.title("Calculator")

# Global variable to store the current expression
expression = ""

# Function to update the expression
def update_expression(num):
    global expression
    expression += str(num)
    equation.set(expression)

# Function to clear the expression
def clear_expression():
    global expression
    expression = ""
    equation.set("")

# Function to evaluate the expression
def evaluate_expression():
    global expression
    try:
        result = eval(expression)
        equation.set(result)
        expression = str(result)
    except Exception as e:
        equation.set("Error")
        expression = ""

# Function to delete a character from the expression
def delete_char():
    global expression
    expression = expression[:-1]
    equation.set(expression)

# Create the entry field for the calculator
equation = StringVar()
entry_field = Entry(window, textvariable=equation, width=20)
entry_field.grid(row=0, column=0, columnspan=4)

# Create the buttons for the calculator
button_1 = Button(window, text="1", width=5, command=lambda: update_expression(1))
button_1.grid(row=1, column=0)

button_2 = Button(window, text="2", width=5, command=lambda: update_expression(2))
button_2.grid(row=1, column=1)

button_3 = Button(window, text="3", width=5, command=lambda: update_expression(3))
button_3.grid(row=1, column=2)

button_4 = Button(window, text="4", width=5, command=lambda: update_expression(4))
button_4.grid(row=2, column=0)

button_5 = Button(window, text="5", width=5, command=lambda: update_expression(5))
button_5.grid(row=2, column=1)

button_6 = Button(window, text="6", width=5, command=lambda: update_expression(6))
button_6.grid(row=2, column=2)

button_7 = Button(window, text="7", width=5, command=lambda: update_expression(7))
button_7.grid(row=3, column=0)

button_8 = Button(window, text="8", width=5, command=lambda: update_expression(8))
button_8.grid(row=3, column=1)

button_9 = Button(window, text="9", width=5, command=lambda: update_expression(9))
button_9.grid(row=3, column=2)

button_0 = Button(window, text="0", width=5, command=lambda: update_expression(0))
button_0.grid(row=4, column=1)

button_add = Button(window, text="+", width=5, command=lambda: update_expression("+"))
button_add.grid(row=1, column=3)

button_subtract = Button(window, text="-", width=5, command=lambda: update_expression("-"))
button_subtract.grid(row=2, column=3)

button_multiply = Button(window, text="*", width=5, command=lambda: update_expression("*"))
button_multiply.grid(row=3, column=3)

button_divide = Button(window, text="/", width=5, command=lambda: update_expression("/"))
button_divide.grid(row=4, column=3)

button_equals = Button(window, text="=", width=5, command=evaluate_expression)
button_equals.grid(row=4, column=2)

button_clear = Button(window, text="C", width=5, command=clear_expression)
button_clear.grid(row=4, column=0)

# Start the main loop
window.mainloop()