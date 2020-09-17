from tzlocal import get_localzone
import sys
z = get_localzone().zone
print (z)
print(type(z))

print(sys.argv[1])
print(sys.argv[2])