from ryu.cmd.manager import main
import sys
sys.argv.append('--verbose')
sys.argv.append('Server.py')
sys.argv.append('--enable-debugger')
main()