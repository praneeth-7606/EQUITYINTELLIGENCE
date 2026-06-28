import sympy as sp

# Define symbols
theta, theta_dot, u, d_theta, d_theta_dot = sp.symbols('theta theta_dot u d_theta d_theta_dot')
M, m, b, I, g, l = sp.symbols('M m b I g l')

# Define denominator and numerator
denom = I * M + I * m + M * l**2 * m + l**2 * m**2 * sp.sin(theta)**2
num = - g * m * (M + m) * sp.sin(theta) - m * sp.sin(theta) * sp.cos(theta) * (- b * theta_dot + d_theta + d_theta_dot + u)

theta_ddot = num / denom

# State vector x = [theta, theta_dot]
# Control input u
# Disturbance vector w = [d_theta, d_theta_dot]
f = sp.Matrix([theta_dot, theta_ddot])
targ_vars = sp.Matrix([theta, theta_dot])
ctrl_vars = sp.Matrix([u])
dist_vars = sp.Matrix([d_theta, d_theta_dot])

# Compute Jacobians
A_x = f.jacobian(targ_vars)
B_x = f.jacobian(ctrl_vars)
B_d = f.jacobian(dist_vars)

# Evaluate at equilibrium: theta = pi, theta_dot = 0, u = 0, d_theta = 0, d_theta_dot = 0
eq_subs = {
    theta: sp.pi,
    theta_dot: 0,
    u: 0,
    d_theta: 0,
    d_theta_dot: 0
}

A_eq = sp.simplify(A_x.subs(eq_subs))
B_eq = sp.simplify(B_x.subs(eq_subs))
Bd_eq = sp.simplify(B_d.subs(eq_subs))

# Print results
print("A:")
print(A_eq)
print("B:")
print(B_eq)
print("B_d:")
print(Bd_eq)
