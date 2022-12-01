*******************
Relation clustering
*******************

Relation clustering allows to create class on SVO extracted during the Syntactic tagging phase.


==================================
Relations clustering configuration
==================================

Example of Configuration:

.. literalinclude:: ../../../app/projects/template/configs/relations.json
    :language: json

Relation clustering configuration is an aggreation of serialize configuration, logger (at top level).
The clustering configuration allows to define embedding server access and clustering algorithms settings:

* **algorithm**: ["kmeans","spericalkmeans" (Not yet available)],
* **number-of-classes**: number of cluster classes,
* **number-of-iterations**: number of kmeans iterations,
* **seed**:kmeans seed
* **batch-size**: we use mini batch kmeans, the batch size if the number of vectors send for partial fit, 
* **embeddings** : embedding server network information (host and port) or aggretion (server-less)
  * server : server configuration
  * aggregation : path to embedding configuration file

Configure Relations clustering logger
-------------------------------------

Logger is configuration at top level of json in *logger* field.

Example of Configuration:

.. literalinclude:: ../configuration/examples/loggerconfiguration.json
    :language: json

The logger fields is:

* **logging-level** 

  It can be set to the following values:

  * **debug** for the debug level and developper information
  * **info** for the level of information
  * **warning** to display only warning and errors
  * **error** to display only error
  * **critical** to display only error



========================
Relation clustering tool
========================

To run the command type simply from tkeir directory:

  .. code-block:: shell 
  
    python3 thot/relation_clustering.py --config=<path to relation configuration file> -i <path to file with syntactic data extracted> -o <path to output folder>



