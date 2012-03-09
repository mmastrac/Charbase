cd static/images/
BATCH_SIZE=1000
for N in {0..200}
do
	zip -9 /tmp/$[N*BATCH_SIZE].zip `seq -f %g.png $[N*BATCH_SIZE] $[(N+1)*BATCH_SIZE-1]` | xargs
done
