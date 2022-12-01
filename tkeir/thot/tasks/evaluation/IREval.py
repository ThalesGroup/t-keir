# -*- coding: utf-8 -*-
"""Evaluation component for Information Retrieval

Author: Eric Blaudez (Eric Blaudez)

Copyright (c) 2022 THALES 
All Rights Reserved.

"""
import json
import os
import json
import gzip
import shutil
import traceback
import time
import datetime


from trectools import TrecRun, TrecQrel, TrecEval
from thot.core.ThotLogger import ThotLogger
import thot.core.Constants as Constants
from thot.tasks.searching.Searching import Searching
from thot.core.ThotLogger import ThotLogger
from thot.tasks.searching.SearchingConfiguration import SearchingConfiguration
import pandas as pd
import matplotlib


class IREval:
    def __init__(self):
        pass

    def generateEvaluation(
        self, evalname="tkeir", searcher=None, data=None, outqrels=None, outqrun=None, outqueries=None, prune=-1, skip_req=-1
    ):
        if not searcher:
            raise ValueError("Searcher file is mandatory")
        if not outqrels:
            raise ValueError("Qrel file is mandatory")
        if not outqrun:
            raise ValueError("Qrun file is mandatory")
        if "queries" in data:
            start_un_recognize_docid = 10000000
            queries = dict()
            docs = set()
            docmapping = dict()
            count_query = 0
            ThotLogger.info("Prune level:" + str(prune))
            for q in data["queries"]:
                if (prune > 0) and (count_query > prune):
                    ThotLogger.info("Stop at Prune level:" + str(prune))
                    break
                outqrels.write(str(q["qid"]) + "\t" + str(0) + "\t" + str(q["docid"]) + "\t" + str(q["relevance"]) + "\n")
                if q["qid"] not in queries:
                    queries[q["qid"]] = {"docs": dict(), "desc": q["description"], "query": q["query"]}
                queries[q["qid"]]["docs"][q["target-document"]] = (q["docid"], q["relevance"])
                docs.add(q["docid"])
                docmapping[q["target-document"]] = q["docid"]
                count_query = len(queries)
            count_query = 0
            for qid in queries:
                if (prune > 0) and (count_query > prune):
                    ThotLogger.info("Stop at Prune level:" + str(prune))
                    break
                ThotLogger.info(str(count_query) + "| Run query:[" + str(qid) + "] : " + queries[qid]["desc"])
                count_query = count_query + 1
                if skip_req != -1 and (skip_req > count_query):
                    continue
                rank = 0
                res_size = 1000
                for f_r in [0]:
                    # for f_r in [0,100,200,300,400,500,600,700,800,900]:
                    try:
                        try:
                            results = searcher.querying_with_doc(
                                {"content": queries[qid]["query"], "from": f_r, "size": res_size}
                            )
                        except Exception as e:
                            ThotLogger.info(Constants.exception_error_and_trace(str(e), str(traceback.format_exc())))
                            results = searcher.querying_with_doc(
                                {"content": queries[qid]["query"][0:4096], "from": f_r, "size": res_size}
                            )
                        count_r = 0
                        if "items" in results:
                            for ri in results["items"]:
                                count_r = count_r + 1
                                docid = start_un_recognize_docid
                                if ri["_source"]["source_doc_id"] in queries[qid]["docs"]:
                                    docid = queries[qid]["docs"][ri["_source"]["source_doc_id"]][0]
                                else:
                                    if ri["_source"]["source_doc_id"] in docmapping:
                                        docid = docmapping[ri["_source"]["source_doc_id"]]
                                    else:
                                        """
                                        if rank > 600:
                                            outqrels.write(str(qid)+"\t"+str(0)+"\t"+str(docid)+"\t0\n")
                                        """
                                        start_un_recognize_docid = start_un_recognize_docid + 1
                                outqrun.write(
                                    str(qid)
                                    + "\tQ0\t"
                                    + str(docid)
                                    + "\t"
                                    + str(rank)
                                    + "\t"
                                    + str(ri["_score"])
                                    + "\t"
                                    + evalname
                                    + "\n"
                                )
                                rank = rank + 1
                        else:
                            ThotLogger.info("QID:" + str(qid) + " at request span " + str(f_r) + " is empty")
                        if count_r < res_size:
                            ThotLogger.info("********* Not enought results on rank span " + str(f_r) + "/" + str(rank))
                        if outqueries and (f_r == 0):
                            now = datetime.datetime.now()
                            outqueries.write(
                                json.dumps(
                                    {
                                        "run-query": qid,
                                        "user-query": queries[qid]["query"],
                                        "date": str(now.strftime("%Y-%m-%d %H:%M:%S")),
                                    }
                                )
                            )
                            outqueries.write("\n")
                            outqueries.write(json.dumps({"es": results, "count-results": count_r, "qid": qid}))
                            outqueries.write("\n")
                        while count_r < res_size:
                            docid = start_un_recognize_docid
                            start_un_recognize_docid = start_un_recognize_docid + 1
                            outqrun.write(str(qid) + "\tQ0\t" + str(docid) + "\t" + str(rank) + "\t0.0\t" + evalname + "\n")
                            count_r = count_r + 1
                            rank = rank + 1

                    except Exception as e:
                        ThotLogger.info(
                            "Error:["
                            + str(qid)
                            + "] : "
                            + Constants.exception_error_and_trace(str(e), str(traceback.format_exc()))
                        )
            return queries
        else:
            raise ValueError("Queries is mandatory")

    def evaluate(self, args_output, args_name, args_queries, args_prune=-1, args_skip_req=-1):
        config = SearchingConfiguration()
        queries = dict()
        with open(args_queries) as q_f:
            queries = json.load(q_f)
            if "system-configuration" in queries:
                with open(queries["system-configuration"]) as f:
                    config.load(f)
                    f.close()
                    ThotLogger.loads(config.logger_config.configuration)
                    ThotLogger.info(queries["system-configuration"] + " loaded.")
            else:
                ThotLogger.loads()
                ThotLogger.error("Configuration file is mandatory")
                raise ValueError("Search configuration is mandatory.")
            q_f.close()
        qrels_file = os.path.join(args_output, "qrels-" + args_name)
        qrun_file = os.path.join(args_output, "qrun-" + args_name)
        queries_file = os.path.join(args_output, "q-" + args_name + ".jsonl")
        with open(qrels_file, "w") as qrel_f:
            with open(qrun_file, "w") as qrun_f:
                with open(queries_file, "w") as queries_f:
                    searcher = Searching(config=config)
                    queries = self.generateEvaluation(
                        evalname=args_name,
                        searcher=searcher,
                        data=queries,
                        outqrels=qrel_f,
                        outqrun=qrun_f,
                        outqueries=queries_f,
                        prune=args_prune,
                        skip_req=args_skip_req,
                    )
                    qrel_f.close()
                    qrun_f.close()
                    queries_f.close()

        with open(qrun_file, "rb") as f_in:
            with gzip.open(qrun_file + ".gz", "wb") as f_out:
                shutil.copyfileobj(f_in, f_out)
                f_out.close()
            f_in.close()
        qresult_file_pq = os.path.join(args_output, "results." + args_name + "-pq.csv")
        qresult_file = os.path.join(args_output, "results." + args_name + ".csv")
        r = TrecRun(qrun_file + ".gz")
        q = TrecQrel(qrels_file)
        te = TrecEval(r, q)

        desc = list(map(lambda x: x[1]["desc"], sorted(queries.items()))) + ["all"]
        num_rel_ret_q = te.get_relevant_retrieved_documents(per_query=True).reset_index()
        num_rel_ret_a = te.get_relevant_retrieved_documents(per_query=False)
        num_rel_q = te.get_relevant_documents(per_query=True).reset_index()
        num_rel_a = te.get_relevant_documents(per_query=False)
        qids = num_rel_q["query"].values.tolist()
        qid_index = dict()
        queryDoc = dict()

        qd = te.qrels.qrels_data[["query", "docid"]].values
        for qd_i in qd:
            if qd_i[0] not in queryDoc:
                queryDoc[qd_i[0]] = set()
            queryDoc[qd_i[0]].add(qd_i[1])

        for i in range(len(qids)):
            qid_index[qids[i]] = i
        df = pd.DataFrame()
        for k in [10, 50, 100, 500]:
            # for k in [5,10,15,20,30,50,100,200,500,1000]:
            pak_q = te.get_precision(depth=k, per_query=True)
            pak_a = te.get_precision(depth=k, per_query=False)
            ndcg_q = te.get_ndcg(depth=k, per_query=True)
            ndcg_a = te.get_ndcg(depth=k, per_query=False)
            rr_q = te.get_reciprocal_rank(depth=k, per_query=True)
            rr_a = te.get_reciprocal_rank(depth=k, per_query=False)
            map_q = te.get_map(depth=k, per_query=True)
            map_a = te.get_map(depth=k, per_query=False)

            pk = list(pak_q["P@" + str(k)].values) + [pak_a]
            ndcg_k = list(ndcg_q["NDCG@" + str(k)].values) + [ndcg_a]
            rr_k = list(rr_q["recip_rank@" + str(k)].values) + [rr_a]
            map_k = list(map_q["MAP@" + str(k)].values) + [map_a]

            run_result = te.run.run_data[te.run.run_data["rank"] <= k][["query", "docid"]]

            run_gini_all = te.run.run_data[te.run.run_data["rank"] <= k][["query", "docid", "score"]].values
            sum_s = 0
            count_s = 0
            lq_s = -1
            gini_coefs = []
            if len(run_gini_all) > 0:
                lq_s = run_gini_all[0][0]
            mean_s = []
            g_score_list = []
            for r_i in run_gini_all:
                if lq_s != r_i[0]:
                    if count_s == 0:
                        mean_s.append(-1)
                        gini_coefs.append(-1)
                    else:
                        mean_s.append(sum_s / count_s)
                        s_gini = 0
                        for s1 in g_score_list:
                            for s2 in g_score_list:
                                s_gini = s_gini + abs(s1 - s2)
                        s_gini = s_gini / (2 * mean_s[-1])
                        gini_coefs.append(s_gini)
                    sum_s = 0
                    count_s = 0
                    g_score_list = []
                    lq_s = r_i[0]
                if r_i[1] < 10000000:
                    sum_s = sum_s + r_i[2]
                    g_score_list.append(r_i[2])
                    count_s = count_s + 1

            if count_s == 0:
                mean_s.append(-1)
                gini_coefs.append(-1)
            else:
                mean_s.append(sum_s / count_s)
                s_gini = 0
                for s1 in g_score_list:
                    for s2 in g_score_list:
                        s_gini = s_gini + abs(s1 - s2)
                s_gini = s_gini / (2 * mean_s[-1])
                gini_coefs.append(s_gini)

            if len(mean_s) == (len(pk) - 1):
                mean_s.append(-1)
            if len(gini_coefs) == (len(pk) - 1):
                gini_coefs.append(-1)

            rr_a = 0
            cr_a = 0
            rel = []
            if len(run_result) > 0:
                merged = pd.merge(run_result, te.qrels.qrels_data)
                result = merged[merged["rel"] > 0]
                for qid in qid_index:
                    count_relevant = num_rel_q[num_rel_q["query"] == qid]["relevant_per_query"].values
                    cr_a = cr_a + list(count_relevant)[0]
                    rr_a = rr_a + result[result["query"] == qid]["query"].count()
                    rel = rel + list(result[result["query"] == qid]["query"].count() / count_relevant)

            if cr_a == 0:
                cr_a = 1
            rel = rel + [rr_a / cr_a]
            # r = [rr_a/cr_a]

            f1 = []
            for kk in range(len(pk)):
                s = rel[kk] + pk[kk]
                if s > 0.0:
                    f1.append(2 * pk[kk] * rel[kk] / s)
                else:
                    f1.append(0.0)

            if len(desc) == len(pk):
                df["desc"] = desc
            if len(mean_s) == len(pk):
                df["Mean-Score@" + str(k)] = mean_s

            df["P@" + str(k)] = pk
            if len(rel) == len(pk):
                df["R@" + str(k)] = rel
            if len(f1) == len(pk):
                df["F1@" + str(k)] = f1
            if len(ndcg_k) == len(pk):
                df["NDCG@" + str(k)] = ndcg_k
            if len(map_k) == len(pk):
                df["MAP@" + str(k)] = map_k
            if len(rr_k) == len(pk):
                df["recip_rank@" + str(k)] = rr_k
            if len(gini_coefs) == len(pk):
                df["gini@" + str(k)] = gini_coefs

        recalls = num_rel_q["relevant_per_query"].values.tolist()
        qids_ret = num_rel_ret_q["query"].values.tolist()
        q_rel = num_rel_ret_q["rel"].values.tolist()
        for vi in range(len(qids_ret)):
            recalls[qid_index[qids_ret[vi]]] = q_rel[vi] / recalls[qid_index[qids_ret[vi]]]
        qids = set(qids)
        qids_ret = set(qids_ret)
        diff_q = qids - qids_ret
        for k in diff_q:
            recalls[qid_index[k]] = 0

        # r = (num_rel_ret_q["rel"].values / num_rel_q["relevant_per_query"].values).tolist()
        ra = num_rel_ret_a / num_rel_a
        rra = recalls + [ra]
        if len(rra) == len(pk):
            df["R"] = rra
        # df["R"] = [ra]
        df.to_csv(qresult_file, index=False)

    def evaluateQuery(self, query, document, config, args_output, args_name):
        args_query = os.path.join(args_output, args_name + "-query.json")
        qrun = {
            "run-name": "Query system with the queries written by a human",
            "system-configuration": config,
            "queries": [
                {
                    "description": "online query",
                    "query": query,
                    "target-document": document,
                    "qid": 1,
                    "docid": "1",
                    "relevance": 1,
                }
            ],
        }
        with open(args_query, "w") as q_f:
            json.dump(qrun, q_f)
            q_f.close()
            self.evaluate(args_output, args_name, args_query)

    def doStat(self, output, csvs):
        for csv in csvs:
            df = pd.read_csv(csv)
            print(df.describe())
