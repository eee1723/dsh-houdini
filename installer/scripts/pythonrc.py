# Only capture a small installation-state snapshot at process startup.
# No hashing, network, process probes, Node or DSH on the GUI thread.
import dsh_bootstrap
dsh_bootstrap.initialize()
