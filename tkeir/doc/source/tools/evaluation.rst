**********
Evaluation
**********

The evaluation tools allows to evaluate the technical components of T-Keir

=====================
Experimental protocol
=====================

Each subsystem (POS, NER, Summary, ...) are evaluated by using K-Folding according to their associated metrics. 
The evaluation is performed in 2 steps:

  * Perform training by using cross-validation : Train on (K-1) sub-dataset test on last fold (use a different validation dataset during training to display learning curves) 
  * Test on test corpus

To make results comparable we can use as baseline the results on Vanilla T-Keir tools


Raw Evaluation
--------------

  * Evaluation each task separately and evaluate according to the task metrics
  * Produce a report (JSON file) containing learning curve, cross validation results, test results


Dataset Transformation and evaluation
-------------------------------------
  
  * When Input model size is pre-defined in Neural networks model :

    * Evaluate models by using an hard cut strategy (Baseline)
    * Evaluate models by using sentence splits
    * Evaluate models by using a sliding window
    * For tagging models split into sentences

  * Automatic summary case

    * Generate corpus (train,dev,test) by using fuzzy distance to get search target summary in the text, this allows to take account of small variations 
    



Language transfert evaluation (for multitask models)
----------------------------------------------------

  * Train on a pre-defined set of language (with Raw Evaluation strategy)
  * Evaluate on language not present in training dataset
  * Produce a report (JSON file) containing learning curve, cross validation results, test results


=======
Metrics
=======

Taggers
-------

Taggers are tools emitting a tag on token or a sequence of tokens (e.g. : POS tagging, NER).
The metric used are F_Beta (generally F1), precision and recall

Automatic Summary
-----------------

The traditional metric used is ROUGE score

Question and Answering
----------------------

The metrics are BLEU score and METEOR

Classification tasks
--------------------

Generally accuracy is used. 


Information retrieval tasks
---------------------------

Here the set a mesure provided by trec-eval are used (precision,recall,F-measure, MAP, ...)


==============
Error Analysis
==============

  * For taggers and classification confusion matrix is computed.
  * For tagging/classication models try to explain decision by using 
  
    * Partial Dependence, 
    * Individual Conditional Expectation, 
    * LIME, 
    * SHAP, 
    * Accumulated Local Effects (ALE) Plot

================
Evaluation tools
================

Taggers
-------

Classification
--------------

Question/Answering
------------------

Automatic Summary
-----------------

Information retrieval
---------------------

