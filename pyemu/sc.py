from __future__ import print_function, division
import numpy as np
import pandas as pd
from pyemu.la import LinearAnalysis
from pyemu.mat import Cov, Matrix

class Schur(LinearAnalysis):
    """derived type for posterior covariance analysis using Schur's complement

    Note:
        Same call signature as the base LinearAnalysis class
    """
    def __init__(self,jco,**kwargs):
        self.__posterior_prediction = None
        self.__posterior_parameter = None
        super(Schur,self).__init__(jco,**kwargs)


    @property
    def pandas(self):
        """get a pandas dataframe of prior and posterior for all predictions
        """
        names,prior,posterior = [],[],[]
        for iname,name in enumerate(self.posterior_parameter.row_names):
            names.append(name)
            posterior.append(np.sqrt(float(
                self.posterior_parameter[iname, iname]. x)))
            iprior = self.parcov.row_names.index(name)
            prior.append(np.sqrt(float(self.parcov[iprior, iprior].x)))
        for pred_name, pred_var in self.posterior_prediction.items():
            names.append(pred_name)
            posterior.append(np.sqrt(pred_var))
            prior.append(self.prior_prediction[pred_name])
        return pd.DataFrame({"posterior": posterior, "prior": prior},
                                index=names)

    @property
    def posterior_parameter(self):
        """get the posterior parameter covariance matrix
        """
        if self.__posterior_parameter is not None:
            return self.__posterior_parameter
        else:
            self.clean()
            self.log("Schur's complement")
            r = (self.xtqx + self.parcov.inv).inv
            assert r.row_names == r.col_names
            self.__posterior_parameter = Cov(r.x, row_names=r.row_names,
                                             col_names=r.col_names)
            self.log("Schur's complement")
            return self.__posterior_parameter

    @property
    def map_parameter_estimate(self):
        res = self.pst.res
        assert res is not None
        # build the prior expectation parameter vector
        prior_expt = self.pst.parameter_data.loc[:,["parval1"]].copy()
        islog = self.pst.parameter_data.partrans == "log"
        prior_expt.loc[islog] = prior_expt.loc[islog].apply(np.log10)
        prior_expt = Matrix.from_dataframe(prior_expt)
        prior_expt.col_names = ["prior_expt"]
        # build the residual vector
        res_vec = Matrix.from_dataframe(res.loc[:,["residual"]])

        # form the terms of Schur's complement
        b = self.parcov * self.jco.T
        c = ((self.jco * self.parcov * self.jco.T) + self.obscov).inv
        bc = Matrix((b * c).x, row_names=b.row_names, col_names=c.col_names)

        # calc posterior expectation
        upgrade = bc * res_vec
        upgrade.col_names = ["prior_expt"]
        post_expt = prior_expt + upgrade

        # post processing - back log transform
        post_expt = pd.DataFrame(data=post_expt.x,index=post_expt.row_names,
                                 columns=["post_expt"])
        post_expt.loc[:,"prior_expt"] = prior_expt.x.flatten()
        post_expt.loc[islog,:] = 10.0**post_expt.loc[islog,:]
        # unc_sum = self.get_parameter_summary()
        # post_expt.loc[:,"standard_deviation"] = unc_sum.post_var.apply(np.sqrt)
        post_expt.sort_index(inplace=True)
        return post_expt

    @property
    def map_forecast_estimate(self):
        assert self.forecasts is not None
        islog = self.pst.parameter_data.partrans == "log"
        par_map = self.map_parameter_estimate
        par_map.loc[islog,:] = np.log10(par_map.loc[islog,:])
        par_map = Matrix.from_dataframe(par_map)
        posts,priors = [],[]
        for forecast in self.forecasts:
            fname = forecast.col_names[0]
            pr = self.pst.res.loc[fname,"modelled"]
            priors.append(pr)
            posts.append(pr + (forecast.T * par_map).x[0, 0])
        return pd.DataFrame(data=np.array([priors,posts]).transpose(),
                            columns=["prior_expt","post_expt"],
                            index=self.forecast_names)

    @property
    def posterior_forecast(self):
        """thin wrapper around posterior_prediction
        """
        return self.posterior_prediction

    @property
    def posterior_prediction(self):
        """get a dict of posterior prediction variances
        """
        if self.__posterior_prediction is not None:
            return self.__posterior_prediction
        else:
            if self.predictions is not None:
                self.log("propagating posterior to predictions")
                pred_dict = {}
                for prediction in self.predictions:
                    var = (prediction.T * self.posterior_parameter
                           * prediction).x[0, 0]
                    pred_dict[prediction.col_names[0]] = var
                self.__posterior_prediction = pred_dict
                self.log("propagating posterior to predictions")
            else:
                self.__posterior_prediction = {}
            return self.__posterior_prediction

    def get_parameter_summary(self,include_map=False):
        """get a summary of the parameter uncertainty
        Parameters:
        ----------
            include_map : bool (optional)
                if True, add the prior and posterior expectations
                and report standard deviation instead of variance
        Returns:
        -------
            pd.DataFrame() of prior,posterior variances and percent
            uncertainty reduction of each parameter
        Raises:
            None
        """
        prior_mat = self.parcov.get(self.posterior_parameter.col_names)
        if prior_mat.isdiagonal:
            prior = prior_mat.x.flatten()
        else:
            prior = np.diag(prior_mat.x)
        post = np.diag(self.posterior_parameter.x)
        if include_map:
            par_data = self.map_parameter_estimate
            prior = pd.DataFrame(data=prior,index=prior_mat.col_names)
            islog = self.pst.parameter_data.partrans == "log"
            par_data.loc[islog,:] = np.log10(par_data.loc[islog,:])
            par_data.loc[:,"prior_stdev"] = prior
            post = pd.DataFrame(data=post,index=prior.index)
            par_data.loc[:,"post_stdev"] = post
            par_data.loc[:,"is_log"] = islog
            return par_data
        else:
            ureduce = 100.0 * (1.0 - (post / prior))

            return pd.DataFrame({"prior_var":prior,"post_var":post,
                                     "percent_reduction":ureduce},
                                    index=self.posterior_parameter.col_names)

    def get_forecast_summary(self, include_map=False):
        """get a summary of the forecast uncertainty
        Parameters:
        ----------
            None
        Returns:
        -------
            pd.DataFrame() of prior,posterior variances and percent
            uncertainty reduction of each forecast
        """
        sum = {"prior_var":[], "post_var":[], "percent_reduction":[]}
        for forecast in self.prior_forecast.keys():
            pr = self.prior_forecast[forecast]
            pt = self.posterior_forecast[forecast]
            ur = 100.0 * (1.0 - (pt/pr))
            sum["prior_var"].append(pr)
            sum["post_var"].append(pt)
            sum["percent_reduction"].append(ur)
        df = pd.DataFrame(sum,index=self.prior_forecast.keys())

        if include_map:
            df.loc[:,"prior_stdev"] = df.pop("prior_var").apply(np.sqrt)
            df.loc[:,"post_stdev"] = df.pop("post_var").apply(np.sqrt)
            df.pop("percent_reduction")
            forecast_map = self.map_forecast_estimate
            df.loc[:,"prior_expt"] = forecast_map.prior_expt
            df.loc[:,"post_expt"] = forecast_map.post_expt
            return df
        return pd.DataFrame(sum,index=self.prior_forecast.keys())

    def __contribution_from_parameters(self, parameter_names):
        """get the prior and posterior uncertainty reduction as a result of
        some parameter becoming perfectly known
        Parameters:
        ----------
            parameter_names (list of str) : parameter that are perfectly known
        Returns:
        -------
            dict{prediction name : [prior uncertainty w/o parameter_names,
                % posterior uncertainty w/o parameter names]}
        """


        #get the prior and posterior for the base case
        bprior,bpost = self.prior_prediction, self.posterior_prediction
        #get the prior and posterior for the conditioned case
        la_cond = self.get_conditional_instance(parameter_names)
        cprior,cpost = la_cond.prior_prediction, la_cond.posterior_prediction
        return cprior,cpost

    def get_conditional_instance(self, parameter_names):
        if not isinstance(parameter_names, list):
            parameter_names = [parameter_names]

        for iname, name in enumerate(parameter_names):
            parameter_names[iname] = name.lower()
            assert name.lower() in self.jco.col_names,\
                "contribution parameter " + name + " not found jco"
        keep_names = []
        for name in self.jco.col_names:
            if name not in keep_names:
                keep_names.append(name)
        if len(keep_names) == 0:
            raise Exception("Schur.contribution_from_parameters: " +
                            "atleast one parameter must remain uncertain")
        #get the reduced predictions
        if self.predictions is None:
            raise Exception("Schur.contribution_from_parameters: " +
                            "no predictions have been set")
        cond_preds = []
        for pred in self.predictions:
            cond_preds.append(pred.get(keep_names, pred.col_names))
        la_cond = Schur(jco=self.jco.get(self.jco.row_names, keep_names),
                        parcov=self.parcov.condition_on(parameter_names),
                        obscov=self.obscov, predictions=cond_preds,verbose=False)
        return la_cond

    def get_par_contribution(self,parlist_dict=None):
        """get a dataframe the prior and posterior uncertainty
        reduction as a result of
        some parameter becoming perfectly known
        Parameters:
        ----------
            parlist_dict (dict of list of str) : groups of parameters
                that are to be treated as perfectly known.  key values become
                row labels in dataframe
        Returns:
        -------
            dataframe[parlist_dict.keys(),(forecast_name,<prior,post>)
                multiindex dataframe of Schur's complement results for each
                group of parameters in parlist_dict values.
        """
        self.log("calculating contribution from parameters")
        if parlist_dict is None:
            parlist_dict = dict(zip(self.pst.parameter_data.parnme,self.pst.parameter_data.parnme))
        else:
            if type(parlist_dict) == list:
                parlist_dict = dict(zip(parlist_dict,parlist_dict))

        results = {}
        names = ["base"]
        for forecast in self.prior_forecast.keys():
            pr = self.prior_forecast[forecast]
            pt = self.posterior_forecast[forecast]
            reduce = 100.0 * ((pr - pt) / pr)
            results[(forecast,"prior")] = [pr]
            results[(forecast,"post")] = [pt]
            results[(forecast,"percent_reduce")] = [reduce]
        for case_name,par_list in parlist_dict.items():
            names.append(case_name)
            self.log("calculating contribution from: " + str(par_list) + '\n')
            case_prior,case_post = self.__contribution_from_parameters(par_list)
            self.log("calculating contribution from: " + str(par_list) + '\n')
            for forecast in case_prior.keys():
                pr = case_prior[forecast]
                pt = case_post[forecast]
                reduce = 100.0 * ((pr - pt) / pr)
                results[(forecast, "prior")].append(pr)
                results[(forecast, "post")].append(pt)
                results[(forecast, "percent_reduce")].append(reduce)

        df = pd.DataFrame(results,index=names)
        self.log("calculating contribution from parameters")
        return df

    def get_par_group_contribution(self):
        """get the forecast uncertainty contribution from each parameter
        group.  Just some sugar for get_contribution_dataframe()
        """
        pargrp_dict = {}
        par = self.pst.parameter_data
        groups = par.groupby("pargp").groups
        for grp,idxs in groups.items():
            pargrp_dict[grp] = list(par.loc[idxs,"parnme"])
        return self.get_par_contribution(pargrp_dict)

    def get_added_obs_importance(self,obslist_dict=None,base_obslist=None,
                                 reset_zero_weight=False):
        """get a dataframe fo the posterior uncertainty
        as a results of added some observations
        Parameters:
        ----------
            obslist_dict (dict of list of str) : groups of observations
                that are to be treated as lost.  key values become
                row labels in result dataframe. If None, then test every obs
            base_obslist (list of str) : observation names to treat as
                the "existing" observations.  The values of obslist_dict
                will be added to this list.  If None, then each list in the
                values of obslist_dict will be treated as an individual
                calibration dataset
            reset_zero_weight : (bool or float) a flag to reset observations
                with zero weight in either obslist_dict or base_obslist.
                If the value of reset_zero_weights can be cast to a float,
                then that value will be assigned to zero weight obs.  Otherwise,
                zero weight obs will be given a weight of 1.0
        Returns:
        -------
            dataframe[obslist_dict.keys(),(forecast_name,post)
                multiindex dataframe of Schur's complement results for each
                group of observations in obslist_dict values.
        Note:
        ----
            all observations listed in obslist_dict and base_obslist with zero
            weights will be dropped unless reset_zero_weight is set
        """

        if obslist_dict is not None:
            if type(obslist_dict) == list:
                obslist_dict = dict(zip(obslist_dict,obslist_dict))



        reset = False
        if reset_zero_weight is not False:
            if not self.obscov.isdiagonal:
                raise NotImplementedError("cannot reset weights for non-"+\
                                          "diagonal obscov")
            reset = True
            try:
                weight = float(reset_zero_weight)
            except:
                weight = 1.0
            self.logger.statement("resetting zero weights to {0}".format(weight))
            # make copies of the original obscov and pst
            org_obscov = self.obscov.get(self.obscov.row_names)
            org_pst = self.pst.get()

        obs = self.pst.observation_data
        obs.index = obs.obsnme

        # if we don't care about grouping obs, then just reset all weights at once
        if base_obslist is None and obslist_dict is None and reset:
            obs.loc[obs.weight==0.0,"weight"] = weight

        # if needed reset the zero-weight obs in base_obslist
        if base_obslist is not None and reset:
            self.log("resetting zero weight obs in base_obslist")
            self.pst.adjust_weights_by_list(base_obslist, weight)
            self.log("resetting zero weight obs in base_obslist")

        if base_obslist is None:
            base_obslist = []

        # if needed reset the zero-weight obs in obslist_dict
        if obslist_dict is not None and reset:
            for case,obslist in obslist_dict.items():
                if not isinstance(obslist,list):
                    obslist_dict[case] = [obslist]
                inboth = set(base_obslist).intersection(set(obslist))
                if len(inboth) > 0:
                    raise Exception("observation(s) listed in both "+\
                                    "base_obslist and obslist_dict: "+\
                                    ','.join(inboth))
                self.log("resetting zero weight obs in {0}".format(case))
                self.pst.adjust_weights_by_list(obslist, weight)
                self.log("resetting zero weight obs in {0}".format(case))

        # for a comprehensive obslist_dict
        if obslist_dict is None and reset:
            obs = self.pst.observation_data
            obs.index = obs.obsnme
            onames = [name for name in self.pst.zero_weight_obs_names
                      if name in self.jco.obs_names]
            obs.loc[onames,"weight"] = weight

        if obslist_dict is None:
            obslist_dict = dict(zip(self.pst.nnz_obs_names,self.pst.nnz_obs_names))

        # reset the obs cov from the newly adjusted weights
        if reset:
            self.log("resetting self.obscov")
            self.reset_obscov(self.pst)
            self.log("resetting self.obscov")

        results = {}
        names = ["base"]

        if base_obslist is None or len(base_obslist) == 0:
            self.logger.statement("no base observation passed, 'base' case"+
                                  " is just the prior of the forecasts")
            for forecast,pr in self.prior_forecast.items():
                results[forecast] = [pr]
            # reset base obslist for use later
            base_obslist = []

        else:
            base_posterior = self.get(par_names=self.jco.par_names,
                                      obs_names=base_obslist).posterior_forecast
            for forecast,pt in base_posterior.items():
                results[forecast] = [pt]

        for case_name,obslist in obslist_dict.items():
            names.append(case_name)
            if not isinstance(obslist,list):
                obslist = [obslist]
            self.log("calculating importance of observations by adding: " +
                     str(obslist) + '\n')
            # this case is the combination of the base obs plus whatever unique
            # obs names in obslist
            case_obslist = list(base_obslist)
            dedup_obslist = [oname for oname in obslist if oname not in case_obslist]
            case_obslist.extend(dedup_obslist)
            case_post = self.get(par_names=self.jco.par_names,
                                 obs_names=case_obslist).posterior_forecast
            for forecast,pt in case_post.items():
                results[forecast].append(pt)
            self.log("calculating importance of observations by adding: " +
                     str(obslist) + '\n')
        df = pd.DataFrame(results,index=names)


        if reset:
            self.reset_obscov(org_obscov)
            self.reset_pst(org_pst)

        return df

    def get_removed_obs_importance(self,obslist_dict=None,
                                   reset_zero_weight=False):
        """get a dataframe the posterior uncertainty
        as a result of losing some observations
        Parameters:
        ----------
            obslist_dict (dict of list of str, or just list of str) : groups of observations
                that are to be treated as lost.  key values become
                row labels in result dataframe. If None, then test every
                (nonzero weight - see reset_zero_weight) observation
            reset_zero_weight : (bool or float) a flag to reset observations
                with zero weight in obslist_dict.
                If the value of reset_zero_weights can be cast to a float,
                then that value will be assigned to zero weight obs.  Otherwise,
                zero weight obs will be given a weight of 1.0

        Returns:
        -------
            dataframe[obslist_dict.keys(),(forecast_name,post)
                multiindex dataframe of Schur's complement results for each
                group of observations in obslist_dict values.

        Note:
        ----
            all observations listed in obslist_dict with zero
            weights will be dropped unless reset_zero_weight is set
        """

        if obslist_dict is not None:
            if type(obslist_dict) == list:
                obslist_dict = dict(zip(obslist_dict,obslist_dict))


        reset = False
        if reset_zero_weight is not False:
            if not self.obscov.isdiagonal:
                raise NotImplementedError("cannot reset weights for non-"+\
                                          "diagonal obscov")
            reset = True
            try:
                weight = float(reset_zero_weight)
            except:
                weight = 1.0
            self.logger.statement("resetting zero weights to {0}".format(weight))
            # make copies of the original obscov and pst
            org_obscov = self.obscov.get(self.obscov.row_names)
            org_pst = self.pst.get()

        self.log("calculating importance of observations")
        if reset and obslist_dict is None:
            obs = self.pst.observation_data
            obs.loc[obs.weight==0.0,"weight"] = weight

        if obslist_dict is None:
            obslist_dict = dict(zip(self.pst.nnz_obs_names,
                                        self.pst.nnz_obs_names))


        elif reset:
            self.pst.observation_data.index = self.pst.observation_data.obsnme
            for name,obslist in obslist_dict.items():
                self.log("resetting weights in obs in group {0}".format(name))
                self.pst.adjust_weights_by_list(obslist,weight)
                self.log("resetting weights in obs in group {0}".format(name))

        for case,obslist in obslist_dict.items():
            if not isinstance(obslist,list):
                obslist = [obslist]
            obslist_dict[case] = obslist


        if reset:
            self.log("resetting self.obscov")
            self.reset_obscov(self.pst)
            self.log("resetting self.obscov")

        results = {}
        names = ["base"]
        for forecast,pt in self.posterior_forecast.items():
            results[forecast] = [pt]
        for case_name,obslist in obslist_dict.items():
            if not isinstance(obslist,list):
                obslist = [obslist]
            names.append(case_name)
            self.log("calculating importance of observations by removing: " +
                     str(obslist) + '\n')
            # check for missing names
            missing_onames = [oname for oname in obslist if oname not in self.jco.obs_names]
            if len(missing_onames) > 0:
                raise Exception("case {0} has observation names ".format(case_name) + \
                                "not found: " + ','.join(missing_onames))
            # find the set difference between obslist and jco obs names
            diff_onames = [oname for oname in self.jco.obs_names if oname not in obslist]

            # calculate the increase in forecast variance by not using the obs
            # in obslist
            case_post = self.get(par_names=self.jco.par_names,
                                 obs_names=diff_onames).posterior_forecast

            for forecast,pt in case_post.items():
                results[forecast].append(pt)
        df = pd.DataFrame(results,index=names)
        self.log("calculating importance of observations by removing: " +
                     str(obslist) + '\n')

        if reset:
            self.reset_obscov(org_obscov)
            self.reset_pst(org_pst)
        return df

    def get_removed_obs_group_importance(self):
        obsgrp_dict = {}
        obs = self.pst.observation_data
        obs.index = obs.obsnme
        obs = obs.loc[self.jco.row_names,:]
        groups = obs.groupby("obgnme").groups
        for grp, idxs in groups.items():
            obsgrp_dict[grp] = list(obs.loc[idxs,"obsnme"])
        return self.get_removed_obs_importance(obsgrp_dict)


    def next_most_important_added_obs(self,forecast=None,niter=3, obslist_dict=None,
                                      base_obslist=None,
                                      reset_zero_weight=False):
        """find the most important observation(s) by sequentailly evaluating
        the importance of the observations in obslist_dict.
        Parameters:
        ----------
            forecast : name of the forecast to use in the ranking process.  If
                more than one forecast has been listed, this argument is required
            niter : number of sequential iterations
            obslist_dict (dict of list of str) : groups of observations
                that are to be treated as lost.  key values become
                row labels in result dataframe. If None, then test every obs
            base_obslist (list of str) : observation names to treat as
                the "existing" observations.  The values of obslist_dict
                will be added to this list.  If None, then each list in the
                values of obslist_dict will be treated as an individual
                calibration dataset
            reset_zero_weight : (bool or float) a flag to reset observations
                with zero weight in either obslist_dict or base_obslist.
                If the value of reset_zero_weights can be cast to a float,
                then that value will be assigned to zero weight obs.  Otherwise,
                zero weight obs will be given a weight of 1.0
        Returns:
        -------
            DataFrame with columns = [best obslist_dict key, forecast variance,
                percent reduction for this iteration, percent reduction
                compared to initial base case]
        """

        if forecast is None:
            assert len(self.forecasts) == 1,"forecast arg list one and only one" +\
                                            " forecast"
            forecast = self.forecasts[0].col_names[0]
        #elif forecast not in self.prediction_arg:
        #    raise Exception("forecast {0} not found".format(forecast))

        else:
            forecast = forecast.lower()
            found = False
            for fore in self.forecasts:
                if fore.col_names[0] == forecast:
                    found = True
                    break
            if not found:
                raise Exception("forecast {0} not found".format(forecast))




        if base_obslist:
            obs_being_used = list(base_obslist)
        else:
            obs_being_used = []

        best_case, best_results = [],[]
        for iiter in range(niter):
            self.log("next most important added obs iteration {0}".format(iiter+1))
            df = self.get_added_obs_importance(obslist_dict=obslist_dict,
                                                   base_obslist=obs_being_used,
                                                   reset_zero_weight=reset_zero_weight)

            if iiter == 0:
                init_base = df.loc["base",forecast].copy()
            fore_df = df.loc[:,forecast]
            fore_diff_df = fore_df - fore_df.loc["base"]
            fore_diff_df.sort(inplace=True)
            iter_best_name = fore_diff_df.index[0]
            iter_best_result = df.loc[iter_best_name,forecast]
            iter_base_result = df.loc["base",forecast]
            diff_percent_init = 100.0 * (init_base -
                                              iter_best_result) / init_base
            diff_percent_iter = 100.0 * (iter_base_result -
                                              iter_best_result) / iter_base_result
            self.log("next most important added obs iteration {0}".format(iiter+1))


            best_results.append([iter_best_name,iter_best_result,
                                 diff_percent_iter,diff_percent_init])
            best_case.append(iter_best_name)

            if iter_best_name.lower() == "base":
                break

            if obslist_dict is None:
                onames = [iter_best_name]
            else:
                onames = obslist_dict.pop(iter_best_name)
            if not isinstance(onames,list):
                onames = [onames]
            obs_being_used.extend(onames)
        columns = ["best_obs",forecast+"_variance",
                   "unc_reduce_iter_base","unc_reduce_initial_base"]
        return pd.DataFrame(best_results,index=best_case,columns=columns)

    def next_most_par_contribution(self,niter=3,forecast=None,parlist_dict=None):
        """find the largest parameter(s) contribution for prior and posterior
        forecast  by sequentailly evaluating the contribution of parameters in
        parlist_dict

        Parameters:
        ----------
            forecast : name of the forecast to use in the ranking process.  If
                more than one forecast has been listed, this argument is required
            parlist_dict (dict of list of str) : groups of parameters
                that are to be treated as perfectly known.  key values become
                row labels in dataframe
        Returns:
        -------
            dataframe[parlist_dict.keys(),(forecast_name,<prior,post>)
                multiindex dataframe of Schur's complement results for each
                group of parameters in parlist_dict values.
        """
        if forecast is None:
            assert len(self.forecasts) == 1,"forecast arg list one and only one" +\
                                            " forecast"
        elif forecast not in self.prediction_arg:
            raise Exception("forecast {0} not found".format(forecast))
        org_parcov = self.parcov.get(row_names=self.parcov.row_names)
        if parlist_dict is None:
            parlist_dict = dict(zip(self.pst.adj_par_names,self.pst.adj_par_names))

        base_prior,base_post = self.prior_forecast,self.posterior_forecast
        iter_results = [base_post[forecast].copy()]
        iter_names = ["base"]
        for iiter in range(niter):
            iter_contrib = {forecast:[base_post[forecast]]}
            iter_case_names = ["base"]
            self.log("next most par iteration {0}".format(iiter+1))

            for case,parlist in parlist_dict.items():
                iter_case_names.append(case)
                la_cond = self.get_conditional_instance(parlist)
                iter_contrib[forecast].append(la_cond.posterior_forecast[forecast])
            df = pd.DataFrame(iter_contrib,index=iter_case_names)
            df.sort(columns=forecast,inplace=True)
            iter_best = df.index[0]
            self.logger.statement("next best iter {0}: {1}".format(iiter+1,iter_best))
            self.log("next most par iteration {0}".format(iiter+1))
            if iter_best.lower() == "base":
                break
            iter_results.append(df.loc[iter_best,forecast])
            iter_names.append(iter_best)
            self.reset_parcov(self.parcov.condition_on(parlist_dict.pop(iter_best)))

        self.reset_parcov(org_parcov)
        return pd.DataFrame(iter_results,index=iter_names)

