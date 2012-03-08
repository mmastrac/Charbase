cd static/images/
for N in {0..100}
do
	zip -9 /tmp/$[N*2500].zip `seq -f %g.png $[N*2500] $[(N+1)*2500-1]` | xargs
done
