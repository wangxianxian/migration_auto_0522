#include <stdlib.h>
main()
//example to generate dirty pages and delay migration for demo purposes:
{
unsigned char *array;
long int i,j,k;
unsigned char c;
long int loop=0;
array=malloc(1024*1024*1024);
while(1)
{
for(i=0;i<1024;i++)
{
c=0;
for(j=0;j<1024;j++)
{
c++;
for(k=0;k<1024;k++)
{
array[i*1024*1024+j*1024+k]=c;
}
}
}
loop++;
}
}
