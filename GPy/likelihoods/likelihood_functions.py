# Copyright (c) 2012, 2013 Ricardo Andrade
# Licensed under the BSD 3-clause license (see LICENSE.txt)


import numpy as np
from scipy import stats,special
import scipy as sp
import pylab as pb
from ..util.plot import gpplot
from ..util.univariate_Gaussian import std_norm_pdf,std_norm_cdf
import link_functions

class LikelihoodFunction(object):
    """
    Likelihood class for doing Expectation propagation

    :param Y: observed output (Nx1 numpy.darray)
    ..Note:: Y values allowed depend on the LikelihoodFunction used
    """
    def __init__(self,link):
        if link == self._analytical:
            self.moments_match = self._moments_match_analytical
        else:
            assert isinstance(link,link_functions.LinkFunction)
            self.link = link
            self.moments_match = self._moments_match_numerical

    def _preprocess_values(self,Y):
        return Y

    def _product(self,gp,obs,mu,sigma):
        """
        Product between the cavity distribution and a likelihood factor
        """
        return stats.norm.pdf(gp,loc=mu,scale=sigma) * self._mass(gp,obs)

    def _nlog_product_scaled(self,gp,obs,mu,sigma):
        """
        Negative log-product between the cavity distribution and a likelihood factor
        """
        return .5*((gp-mu)/sigma)**2 + self._nlog_mass(gp,obs)

    def _dnlog_product_dgp(self,gp,obs,mu,sigma):
        """
        Derivative wrt gp of the log-product between the cavity distribution and a likelihood factor
        """
        #return -(gp - mu)/sigma**2 + self._dlog_mass_dgp(gp,obs)
        return (gp - mu)/sigma**2 + self._dnlog_mass_dgp(gp,obs)

    def _d2nlog_product_dgp2(self,gp,obs,mu,sigma):
        """
        Second derivative wrt gp of the log-product between the cavity distribution and a likelihood factor
        """
        #return -1./sigma**2 + self._d2log_mass_dgp2(gp,obs)
        return 1./sigma**2 + self._d2nlog_mass_dgp2(gp,obs)

    def _product_mode(self,obs,mu,sigma):
        """
        Newton's CG method to find the mode in the _product function (cavity x likelihood factor)
        """
        return sp.optimize.fmin_ncg(self._nlog_product_scaled,x0=mu,fprime=self._dnlog_product_dgp,fhess=self._d2nlog_product_dgp2,args=(obs,mu,sigma))


    def _moments_match_numerical(self,obs,tau,v):
        """
        Lapace approximation to calculate the moments mumerically.
        """
        mu = v/tau
        mu_hat = self._product_mode(obs,mu,np.sqrt(1./tau))
        sigma2_hat = 1./(tau + self._d2nlog_mass_dgp2(mu_hat,obs))
        Z_hat = np.exp(-.5*tau*(mu_hat-mu)**2) * self._mass(mu_hat,obs)*np.sqrt(tau*sigma2_hat)
        return Z_hat,mu_hat,sigma2_hat

    """
    def _nlog_predictive_mean_scaled(self,gp,mu,sigma):
        return  .5*((gp-mu)/sigma)**2 - np.log(self.link.inv_transf(gp))

    def _dnlog_predictive_mean_dgp(self,gp,mu,sigma):
        return (gp - mu)/sigma**2 - self.link.dinv_transf_df(gp)/self.link.inv_transf(gp)

    def _d2nlog_predictive_mean_dgp2(self,gp,mu,sigma): #TODO mu is not necessary
        return 1/sigma**2 - (self.link.d2inv_transf_df2(gp) - self.link.dinv_transf_df(gp))/self.link.inv_transf(gp)

    def _predictive_mean(self,mu,sigma):
        return sp.optimize.fmin_ncg(self._nlog_predictive_mean_scaled,x0=mu,fprime=self._dnlog_predictive_mean_dgp,fhess=self._d2nlog_predictive_mean_dgp2,args=(mu,sigma))
    """

    def _nlog_joint_predictive_scaled(self,x,mu,sigma): #TODO not needed
        """
        x = np.array([gp,obs])
        """
        return self._nlog_product_scaled(x[0],x[1],mu,sigma)

    def _gradient_nlog_joint_predictive(self,x,mu,sigma): #TODO not needed
        return np.array((self._dnlog_product_dgp(gp=x[0],obs=x[1],mu=mu,sigma=sigma),self._dnlog_mass_dobs(obs=x[1],gp=x[0])))

    def _hessian_nlog_joint_predictive(self,x,mu,sigma): #TODO not needed
        cross_derivative = self._d2nlog_mass_dcross(gp=x[0],obs=x[1])
        return np.array((self._d2nlog_product_dgp2(gp=x[0],obs=x[1],mu=mu,sigma=sigma),cross_derivative,cross_derivative,self._d2nlog_mass_dobs2(obs=x[1],gp=x[0]))).reshape(2,2)

    def _joint_predictive_mode(self,mu,sigma):
        return sp.optimize.fmin_ncg(self._nlog_joint_predictive_scaled,x0=(mu,self.link.inv_transf(mu)),fprime=self._gradient_nlog_joint_predictive,fhess=self._hessian_nlog_joint_predictive,args=(mu,sigma))

    def predictive_values(self,mu,var):
        """
        Compute  mean, variance and conficence interval (percentiles 5 and 95) of the  prediction
        """
        if isinstance(mu,float) or isinstance(mu,int):
            mu = [mu]
            var = [var]
        pred_mean = []
        pred_var = []
        q1 = []
        q3 = []
        y_range = range(0,250) #TODO fix this range
        marginal_proxy = np.zeros(len(y_range)) #TODO fixed 7?
        for m,s in zip(mu,np.sqrt(var)):
            for g in [m + step*s for step in range(-3,4)]:
                mp = []
                for y in y_range:#*np.int(self.link.inv_transf(mu))): #TODO fix this range
                    mp.append(self._product(g,y,m,s))
                marginal_proxy += mp
            cumulative = np.cumsum(marginal_proxy)/np.sum(marginal_proxy)
            q1.append(cumulative[cumulative<=.025].size) #What if not start in y=0
            q3.append(cumulative[cumulative<=.975].size)

        pred_mean = np.array(pred_mean)[:,None]
        pred_var = np.array(pred_var)[:,None]
        q1 = np.array(q1)[:,None]
        q3 = np.array(q3)[:,None]
        pred_mean = np.zeros(q1.shape) #TODO erase me
        pred_var = np.zeros(q1.shape) #TODO erase me
        return pred_mean, pred_var, q1, q3

    def _nlog_conditional_mean_scaled(self,gp,mu,sigma):
        """
        E(Y_star) = E( E(Y_star|f_star) )
        """
        return ((gp - mu)/sigma)**2 - np.log(self._mean(gp))

    def _dnlog_conditional_mean_dgp(self,gp,mu,sigma):
        return (gp - mu)/sigma**2 - self._dmean_dgp(gp)/self._mean(gp)

    def _d2nlog_conditional_mean_dgp2(self,gp,mu,sigma):
        return 1./sigma**2 - (self._dmean_dgp(gp)/self._mean(gp))**2 + self._d2mean_dgp2(gp)/self._mean(gp)

    def _nlog_exp_conditional_variance_scaled(self,gp,mu,sigma):
        """
        E( V(Y_star|f_star) )
        """
        return ((gp - mu)/sigma)**2 - np.log(self._variance(gp))

    def _dnlog_exp_conditional_variance_dgp(self,gp,mu,sigma):
        return (gp - mu)/sigma**2 - self._dvariance_dgp(gp)/self._variance(gp)

    def _d2nlog_exp_conditional_variance_dgp2(self,gp,mu,sigma):
        return 1./sigma**2 - (self._dvariance_dgp(gp)/self._variance(gp))**2 + self._d2variance_dgp2(gp)/self._variance(gp)

    def _nlog_var_conditional_mean_scaled(self,gp,mu,sigma,predictive_mean):
        """
        V( E(Y_star|f_star) )
        """
        return ((gp - mu)/sigma)**2 - 2*np.log(self._mean(gp)-predictive_mean)

    def _dnlog_var_conditional_mean_dgp(self,gp,mu,sigma,predictive_mean):
        return (gp - mu)/sigma**2 - 2*self._dmean_dgp(gp)/(self._mean(gp)-predictive_mean)

    def _d2nlog_var_conditional_mean_dgp2(self,gp,mu,sigma,predictive_mean):
        return 1./sigma**2 - 2*( (self._dmean_dgp(gp)/(self._mean(gp)-predictive_mean))**2 + self._d2mean_dgp2(gp)/(self._variance(gp)-predictive_mean) )

    def _predictive_mean(self,gp,mu,sigma):
        """
        Laplace approximation to the predictive mean
        """
        maximum = sp.optimize.fmin_ncg(self._nlog_conditional_mean_scaled,x0=self._mean(mu),fprime=self._dnlog_conditional_mean_dgp,fhess=self._d2nlog_conditional_mean_dgp2,args=(mu,sigma))
        mean = np.exp(-self._nlog_conditional_mean_scaled(maximum,mu,sigma))/(np.sqrt(self._d2nlog_conditional_mean_dgp2(gp,mu,sigma))*sigma)
        return mean

    def _predictive_variance(self,gp,mu,sigma,predictive_mean):
        """
        Laplace approximation to the predictive variance
        ------------------------------------------------
        E(Y_star) = E( V(Y_star|f_star) ) + V( E(Y_star|f_star) )
        """
        maximum_1 = sp.optimize.fmin_ncg(self._nlog_exp_conditional_variance_scaled,x0=self._variance(mu),fprime=self._dnlog_exp_conditional_variance_dgp,fhess=self._d2nlog_exp_conditional_variance_dgp2,args=(mu,sigma))
        exp_var = np.exp(-self._nlog_exp_conditional_variance_scaled(maximum_1,mu,sigma))/(np.sqrt(self._d2nlog_exp_conditional_variance_dgp2(gp,mu,sigma))*sigma)

        #(self._mean(mu)-predictive_mean)**2
        maximum_2 = sp.optimize.fmin_ncg(self._nlog_var_conditional_mean_scaled,x0=self._variance(mu),fprime=self._dnlog_var_conditional_mean_dgp,fhess=self._d2nlog_var_conditional_mean_dgp2,args=(mu,sigma,predictive_mean))
        var_exp = np.exp(-self._nlog_var_conditional_mean_scaled(maximum_2,mu,sigma))/(np.sqrt(self._d2nlog_var_conditional_mean_dgp2(gp,mu,sigma))*sigma)

        return exp_var + var_exp


class Binomial(LikelihoodFunction):
    """
    Probit likelihood
    Y is expected to take values in {-1,1}
    -----
    $$
    L(x) = \\Phi (Y_i*f_i)
    $$
    """
    def __init__(self,link=None):
        self._analytical = link_functions.Probit
        if not link:
            link = self._analytical
        super(Binomial, self).__init__(link)

    def _mass(self,gp,obs):
        pass

    def _nlog_mass(self,gp,obs):
        pass

    def _preprocess_values(self,Y):
        """
        Check if the values of the observations correspond to the values
        assumed by the likelihood function.

        ..Note:: Binary classification algorithm works better with classes {-1,1}
        """
        Y_prep = Y.copy()
        Y1 = Y[Y.flatten()==1].size
        Y2 = Y[Y.flatten()==0].size
        assert Y1 + Y2 == Y.size, 'Binomial likelihood is meant to be used only with outputs in {0,1}.'
        Y_prep[Y.flatten() == 0] = -1
        return Y_prep

    def _moments_match_analytical(self,data_i,tau_i,v_i):
        """
        Moments match of the marginal approximation in EP algorithm

        :param i: number of observation (int)
        :param tau_i: precision of the cavity distribution (float)
        :param v_i: mean/variance of the cavity distribution (float)
        """
        z = data_i*v_i/np.sqrt(tau_i**2 + tau_i)
        Z_hat = std_norm_cdf(z)
        phi = std_norm_pdf(z)
        mu_hat = v_i/tau_i + data_i*phi/(Z_hat*np.sqrt(tau_i**2 + tau_i))
        sigma2_hat = 1./tau_i - (phi/((tau_i**2+tau_i)*Z_hat))*(z+phi/Z_hat)
        return Z_hat, mu_hat, sigma2_hat

    def predictive_values(self,mu,var):
        """
        Compute  mean, variance and conficence interval (percentiles 5 and 95) of the  prediction
        :param mu: mean of the latent variable
        :param var: variance of the latent variable
        """
        mu = mu.flatten()
        var = var.flatten()
        mean = stats.norm.cdf(mu/np.sqrt(1+var))
        norm_025 = [stats.norm.ppf(.025,m,v) for m,v in zip(mu,var)]
        norm_975 = [stats.norm.ppf(.975,m,v) for m,v in zip(mu,var)]
        p_025 = stats.norm.cdf(norm_025/np.sqrt(1+var))
        p_975 = stats.norm.cdf(norm_975/np.sqrt(1+var))
        return mean[:,None], np.nan*var, p_025[:,None], p_975[:,None] # TODO: var

class Poisson(LikelihoodFunction):
    """
    Poisson likelihood
    Y is expected to take values in {0,1,2,...}
    -----
    $$
    L(x) = \exp(\lambda) * \lambda**Y_i / Y_i!
    $$
    """
    def __init__(self,link=None):
        self._analytical = None
        if not link:
            link = link_functions.Log()
        super(Poisson, self).__init__(link)

    def _mass(self,gp,obs):
        """
        Mass (or density) function
        """
        return stats.poisson.pmf(obs,self.link.inv_transf(gp))

    def _percentile(self,x,gp,*args): #TODO *args
        return stats.poisson.ppf(x,self.link.inv_transf(gp))

    def _nlog_mass(self,gp,obs):
        """
        Negative logarithm of the un-normalized distribution: factors that are not a function of gp are omitted
        """
        return self.link.inv_transf(gp) - obs * np.log(self.link.inv_transf(gp)) + np.log(special.gamma(obs+1))

    def _dnlog_mass_dgp(self,gp,obs):
        #return self.link.dinv_transf_df(gp) * (obs/self.link.inv_transf(gp) - 1)
        return self.link.dinv_transf_df(gp) * (1. - obs/self.link.inv_transf(gp))

    def _d2nlog_mass_dgp2(self,gp,obs):
        d2_df = self.link.d2inv_transf_df2(gp)
        inv_transf = self.link.inv_transf(gp)
        #return obs * ( d2_df/inv_transf - (self.link.dinv_transf_df(gp)/inv_transf)**2 ) - d2_df
        return obs * ((self.link.dinv_transf_df(gp)/inv_transf)**2 - d2_df/inv_transf) + d2_df

    def _dnlog_mass_dobs(self,obs,gp): #TODO not needed
        #return np.log(self.link.inv_transf(gp)) - special.psi(obs+1)
        return special.psi(obs+1) -  np.log(self.link.inv_transf(gp))

    def _d2nlog_mass_dobs2(self,obs,gp=None): #TODO not needed
        #return -special.polygamma(1,obs)
        return special.polygamma(1,obs)

    def _d2nlog_mass_dcross(self,obs,gp): #TODO not needed
        #return self.link.dinv_transf_df(gp)/self.link.inv_transf(gp)
        return -self.link.dinv_transf_df(gp)/self.link.inv_transf(gp)

    def _mean(self,gp):
        """
        Mass (or density) function
        """
        return self.link.inv_transf(gp)

    def _variance(self,gp):
        return self.link.inv_transf(gp)

    def _dmean_dgp(self,gp):
        return self.link.dinv_transf_df(gp)

    def _d2mean_dgp2(self,gp):
        return self.link.dinv_transf_df(gp)

    def _variance(self,gp):
        """
        Mass (or density) function
        """
        return self.link.inv_transf(gp)

    def _variance(self,gp):
        return self.link.inv_transf(gp)

    def _dvariance_dgp(self,gp):
        return self.link.dinv_transf_df(gp)

    def _d2variance_dgp2(self,gp):
        return self.link.dinv_transf_df(gp)




