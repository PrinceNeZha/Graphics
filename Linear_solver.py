import taichi as ti
import numpy as np
import random,collections

@ti.data_oriented
class LinearSolver:
    def __init__(self,n,A=None,b=None,iterationNum=100,epsilon=1e-6):
        self.n = n
        self.x    = ti.field(dtype = ti.f32,shape = n)
        self.r  = ti.field(dtype = ti.f32,shape = n)
        self.p  = ti.field(dtype = ti.f32,shape = n) #temporary vector for intermedate variables
        self.t  = ti.field(dtype = ti.f32,shape = n)
        self.A  = A 
        self.b  = b 
        self.itrNum = iterationNum
        self.eps = epsilon
        self.x.fill(0) #initial guess

    @ti.kernel
    def Copy(self,dst:ti.template(),src:ti.template()):
        for I in ti.grouped(src):dst[I] = src[I]

    @ti.kernel
    def Residual(self):
        for i in range(self.n):
            self.r[i] = self.b[i]
            for j in range(self.n):
                self.r[i]-=self.A[i,j]*self.x[j]

    @ti.kernel
    def StepJacobi(self):
        for i in range(self.n):
            bi = self.b[i]
            for j in range(self.n):
                if i==j:continue
                bi-=self.A[i,j]*self.x[j]
            self.t[i] = bi/self.A[i,i]
        for i in range(self.n):
            self.x[i] = self.t[i]

    # parallel gauss seidel
    @ti.kernel
    def StepGaussSeidel(self,partition:ti.ext_arr(),partitionSize:ti.u32):
        for s in range(partitionSize):
            i = partition[s]
            bi = self.b[i]
            for j in range(self.n):
                if i==j:continue
                bi-=self.A[i,j]*self.x[j]
            self.x[i] = bi/self.A[i,i]
            
    @ti.kernel
    def StepConjugateGradient(self):
        # calculate t = A*p
        for i in range(self.n):
            self.t[i] = 0.0
            for j in range(self.n):
                self.t[i] += self.A[i,j]*self.p[j]
        # calculate alpha
        alphaNumerator   = 0.0
        alphaDenominator = 0.0
        for i in range(self.n):
            alphaNumerator   += self.r[i]*self.r[i]
            alphaDenominator += self.t[i]*self.p[i] 
        alpha = alphaNumerator/alphaDenominator
        # update x and compute new residual(rn = r - alpha*Ap or rn = b - Ax) and beta
        betaNumerator = 0.0 
        betaDenominator = alphaNumerator
        for i in range(self.n):
            self.x[i] = self.x[i] + alpha*self.p[i]
            self.r[i] = self.r[i] - alpha*self.t[i]
            betaNumerator += self.r[i]*self.r[i]
        beta = betaNumerator/betaDenominator
        #update p
        for i in range(self.n):
            self.p[i] = self.r[i] + beta *self.p[i]

    def GraphColoring(self):
        n = self.n
        g = [[]for _ in range(n)]
        for i in range(n):
            for j in range(n):
                if i==j:continue
                if self.A[i,j]!=0.0:g[i].append(j)
        maxStuckNum,stuckNum = 20,0
        maxColorNum = max(2,max([len(g[i])for i in range(n)])//7.5)
        palette = [set([i for i in range(maxColorNum)])for _ in range(n)]
        u = set([i for i in range(n)])
        c = [0 for _ in range(n)]
        nc = [maxColorNum for _ in range(n)]
        while len(u)>0:
            for i in u:
                c[i] = random.choice(list(palette[i]))
            t = set()
            for i in u:
                distinct = True
                for j in g[i]:
                    if c[j]==c[i]:
                        distinct = False
                        break
                if distinct:
                    for j in g[i] :
                        if c[i] in palette[j]:
                            palette[j].remove(c[i])
                else: t.add(i)
                if len(palette[i])==0:
                    palette.add(nc[i])
                    nc[i]+=1
            if len(u)==len(t):
                stuckNum+=1
                if stuckNum>=maxStuckNum:
                    stuckNum = 0
                    r = random.choice(list(u))
                    palette[r].add(nc[r])
                    nc[r]+=1
            u = t
        m = collections.defaultdict(list)
        for i in range(n):m[c[i]].append(i)
        reorder = []
        for v in m.values():
            reorder.append(np.array(v))
        return reorder
        #     for i in v:
        #         reorder.append(i)
        # return np.array(reorder)

    def SetAb(self,newA,newb):
        if newb.shape!=(self.n,) or newA.shape!=(self.n,self.n):
            print("ERROR: shape not match")
        self.A,self.b = newA,newb

    def Jacobi(self):
        _ = 0
        self.Residual()
        while _<self.itrNum and np.max(np.abs(self.r.to_numpy()))>self.eps:
            self.StepJacobi()
            self.Residual()
            _+=1
        return _

    def GaussSeidel(self):
        _ = 0
        reorder = self.GraphColoring()
        self.Residual()
        while _<self.itrNum and np.max(np.abs(self.r.to_numpy()))>self.eps:
            for partition in reorder:
                self.StepGaussSeidel(partition,partition.size)
            self.Residual()
            _+=1
        return _

    def ConjugateGradient(self):
        _ = 0
        self.Residual()
        self.Copy(self.p,self.r)
        while _<self.itrNum and np.max(np.abs(self.r.to_numpy()))>self.eps:
            self.StepConjugateGradient()
            _+=1
        return _

def LinearSolverTestMain():
    
    ti.init(arch=ti.gpu)
    n  = 7
    b  = ti.field(dtype = ti.f32,shape=n)
    A  = ti.field(dtype = ti.f32,shape=(n,n))

    @ti.kernel
    def Initialize():
        for i in range(n):
            A[i,i] = 2.5
            if i+1<=n-1: A[i,i+1] = -1
            if i-1>=0:   A[i,i-1] = -1
        A[0,n-1]=-1
        A[n-1,0]=-1
        for i in range(n):
            b[i] = 0.0
        b[0] = 1

    Initialize()
    ls = LinearSolver(n)
    ls.SetAb(A,b)

    import time

    print('{0:20}   {1:10}  {2:10}  {3:30}'.format('Method','Time(s)','Iteration Number','Max Residual'))

    ls.x.fill(0)
    start = time.process_time()
    cnt = ls.Jacobi()
    end = time.process_time()
    print('{0:20}   {1:10}  {2:10}  {3:30}'.format('Jacobi',end-start,cnt,np.max(np.abs(ls.r.to_numpy()))))
    
    ls.x.fill(0)
    start = time.process_time()
    cnt = ls.GaussSeidel()
    end = time.process_time()
    print('{0:20}   {1:10}  {2:10}  {3:30}'.format('Gauss-Seidel',end-start,cnt,np.max(np.abs(ls.r.to_numpy()))))

    ls.x.fill(0)
    start = time.process_time()
    cnt = ls.ConjugateGradient()
    end = time.process_time()
    print('{0:20}   {1:10}  {2:10}  {3:30}'.format('Conjugate-Gradient',end-start,cnt,np.max(np.abs(ls.r.to_numpy()))))

LinearSolverTestMain()