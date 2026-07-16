
```python
import math, cmath

def _eigvals(A, maxit=2000, tol=1e-14):
    """实/复方阵的全部特征值(复数):Hessenberg 化 + 带位移 QR + 收缩。"""
    n = len(A)
    if n == 0: return []
    if n == 1: return [complex(A[0][0])]
    H = [[complex(A[i][j]) for j in range(n)] for i in range(n)]
    for k in range(n - 2):                                  # 化为上 Hessenberg
        for i in range(k + 2, n):
            a, b = H[k+1][k], H[i][k]
            r = math.hypot(abs(a), abs(b))
            if r == 0: continue
            c, s = a.conjugate()/r, b.conjugate()/r
            for j in range(n):
                x, y = H[k+1][j], H[i][j]
                H[k+1][j] = c*x + s*y
                H[i][j]   = -s.conjugate()*x + c.conjugate()*y
            for j in range(n):
                x, y = H[j][k+1], H[j][i]
                H[j][k+1] = c.conjugate()*x + s.conjugate()*y
                H[j][i]   = -s*x + c*y
    eig = []; m = n; it = 0
    while m > 0:
        if m == 1:
            eig.append(H[0][0]); break
        l = m - 1
        while l > 0:                                        # 找可收缩的次对角零点
            if abs(H[l][l-1]) <= tol*(abs(H[l-1][l-1]) + abs(H[l][l])):
                H[l][l-1] = 0; break
            l -= 1
        if l == m - 1:
            eig.append(H[m-1][m-1]); m -= 1; it = 0; continue
        if l == m - 2:                                      # 末尾 2x2 直接求根(含复根)
            a,b,c,d = H[m-2][m-2],H[m-2][m-1],H[m-1][m-2],H[m-1][m-1]
            tr = a + d; disc = cmath.sqrt(tr*tr - 4*(a*d - b*c))
            eig.append((tr+disc)/2); eig.append((tr-disc)/2); m -= 2; it = 0; continue
        it += 1
        if it > maxit:
            for i in range(m): eig.append(H[i][i])
            break
        a,b,c,d = H[m-2][m-2],H[m-2][m-1],H[m-1][m-2],H[m-1][m-1]
        tr = a + d; disc = cmath.sqrt(tr*tr - 4*(a*d - b*c))
        l1, l2 = (tr+disc)/2, (tr-disc)/2
        mu = l1 if abs(l1 - d) < abs(l2 - d) else l2         # Wilkinson 位移
        for i in range(m): H[i][i] -= mu
        cs = []
        for k in range(m - 1):                              # QR:Givens 消次对角
            a, b = H[k][k], H[k+1][k]; r = math.hypot(abs(a), abs(b))
            c, s = (1.0+0j, 0j) if r == 0 else (a.conjugate()/r, b.conjugate()/r)
            cs.append((c, s))
            for j in range(k, m):
                x, y = H[k][j], H[k+1][j]
                H[k][j]   = c*x + s*y
                H[k+1][j] = -s.conjugate()*x + c.conjugate()*y
        for k in range(m - 1):                              # RQ
            c, s = cs[k]
            for i in range(min(k + 2, m)):
                x, y = H[i][k], H[i][k+1]
                H[i][k]   = x*c.conjugate() + y*s.conjugate()
                H[i][k+1] = -x*s + y*c
        for i in range(m): H[i][i] += mu
    return eig


def _mat_rank(M, tol=1e-7):
    """复矩阵数值秩:带相对容差的高斯消元。"""
    if not M or not M[0]: return 0
    A = [[complex(v) for v in row] for row in M]
    rows, cols = len(A), len(A[0])
    scale = max((abs(v) for row in A for v in row), default=0.0)
    if scale == 0: return 0
    thr = tol * scale; r = 0
    for col in range(cols):
        piv = max(range(r, rows), key=lambda i: abs(A[i][col]))
        if abs(A[piv][col]) <= thr: continue
        A[r], A[piv] = A[piv], A[r]
        pv = A[r][col]
        for i in range(rows):
            if i != r and A[i][col] != 0:
                f = A[i][col] / pv
                for j in range(col, cols): A[i][j] -= f*A[r][j]
        r += 1
        if r == rows: break
    return r


def _matmul(A, B):
    n, k, m = len(A), len(B), len(B[0]); C = [[0.0]*m for _ in range(n)]
    for i in range(n):
        for p in range(k):
            a = A[i][p]
            if a == 0: continue
            for j in range(m): C[i][j] += a*B[p][j]
    return C

def _transpose(A): return [[A[i][j] for i in range(len(A))] for j in range(len(A[0]))]


def check_kalman_convergence(A, C, W, unit_tol=1e-6, rank_tol=1e-7):
    """
    离散卡尔曼估计器可收敛性判据。返回 (ok, reason, lam)。
      A: n x n 状态矩阵;  C: p x n 输出矩阵
      W: n x n 过程噪声协方差 = G*Q*G'(未启用 G 时 W = Q)
    连续时间只需把 |λ|>=1 换成 Re(λ)>=0、|λ|==1 换成 |Re(λ)|<=tol。
    """
    n = len(A)
    if n == 0 or any(len(r) != n for r in A):
        raise ValueError("A must be a non-empty square matrix")
    if any(len(r) != n for r in C):
        raise ValueError("C column count must equal order of A")
    if len(W) != n or any(len(r) != n for r in W):
        raise ValueError("W must be n x n (= G*Q*G')")
    for lam in _eigvals(A):
        mag = abs(lam)
        AmI = [[A[i][j] - (lam if i == j else 0) for j in range(n)] for i in range(n)]
        if mag >= 1 - unit_tol:                              # 条件 A:不稳定/临界极点须可观测
            OC = [row[:] for row in AmI] + [[complex(v) for v in row] for row in C]
            if _mat_rank(OC, rank_tol) < n:
                return (False, "unobservable_unstable_pole", lam)
        if abs(mag - 1.0) <= unit_tol:                       # 条件 B:圆上极点须被过程噪声激励
            AW = [AmI[i] + [complex(W[i][j]) for j in range(n)] for i in range(n)]
            if _mat_rank(AW, rank_tol) < n:
                return (False, "uncontrollable_pole_on_unit_circle", lam)
    return (True, None, None)

```


放在 validate_block_matrix(半正定校验)通过之后执行,并且只在矩阵是静态参数时才校验(Input port 模式下 A/C 是运行时输入,拿不到):

```python
# ... 前面 QData/RData/NData 解析与 validate_block_matrix 保持不变 ...

model_source = getEntityMaskAttr(maskEntity, "Model source")
if model_source == "Individual A, B, C, D matrices":
    A = parse_2d_float_array(getEntityMaskAttrToken(maskEntity, "A"))
    C = parse_2d_float_array(getEntityMaskAttrToken(maskEntity, "C"))
    Q = QData
    n = len(A)

    # 未启用 G/H 时默认 G=I => W=Q;启用时 W = G*Q*G'
    try:
        G = parse_2d_float_array(getEntityMaskAttrToken(maskEntity, "G"))
    except Exception:
        G = None
    W = Q if G is None else _matmul(_matmul(G, Q), _transpose(G))

    ok, reason, lam = check_kalman_convergence(A, C, W)
    if not ok:
        pole = ("{:.4g}".format(lam.real) if abs(lam.imag) < 1e-9
                else "{:.4g}{:+.4g}j".format(lam.real, lam.imag))
        if reason == "unobservable_unstable_pole":
            raise Exception(
                "Cannot compute a convergent Kalman estimator: unstable pole %s of A "
                "is not observable through C. (A 的不稳定极点 %s 不能被 C 观测,"
                "请确保所有不稳定极点可观测)" % (pole, pole))
        else:
            raise Exception(
                "Cannot compute a convergent Kalman estimator: pole %s of A lies on the "
                "unit circle and is not excited by the process noise Q/G. "
                "(A 在单位圆上的极点 %s 未被过程噪声激励,请把该极点移入单位圆内——"
                "例如把 1 改成 0.1——或增大对应状态的 Q)" % (pole, pole))
    
```
