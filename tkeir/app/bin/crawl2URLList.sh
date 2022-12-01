#!/bin/bash

outdir=/tmp/httrack
proxy=""

if [ $1 ]; 
then
    crawl_host=$1
fi

if [ $2 ];
then
    outdir=$2
fi

if [ $3 ];
then
   proxy="-P $3"
   proxy=`echo $proxy | sed -e 's/https:\/\///g' | sed -e 's/http:\/\///g'`
fi

sub_host=`echo $crawl_host | sed -e 's/https:\/\///g' | sed -e 's/http:\/\///g'`
mkdir -p $outdir

if [ ! -z $sub_host ];
then
    echo "HOST:$sub_host, PROXY:$proxy"
    httrack $proxy --mirror --user-agent "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:63.0)" --robots=0 $crawl_host -O $outdir +$sub_host/* -v

    pushd $outdir/hts-cache
    cat new.txt | grep text/html | grep "added ('OK')" | cut -d$'\t' -f 8 > $outdir/url.lst
    #python3 ../app/projects/ai4eu/resources/accumos/acumosCrawler.py acumosCrawler.py -p thales-search.pem -u https://aiexp.ai4europe.eu:31944
    
else
    echo -ne "usage crawl2URLList.sh http[s]://fqdn outdir\n"
    exit
fi

