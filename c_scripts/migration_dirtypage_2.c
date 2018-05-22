#include <stdlib.h>
#include <stdio.h>
#include <signal.h>
int main()
{
void wakeup();
signal(SIGALRM,wakeup);
alarm(120);
char *buf = (char *) calloc(40960, 4096);
while (1) {
int i;
for (i = 0; i < 40960 * 4; i++) {
buf[i * 4096 / 4]++;
}
printf(".");
}
}
void wakeup()
{
exit(0);
}
