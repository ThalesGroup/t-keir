for h in `env | grep _HOST`; do export `echo $h | sed -e 's/0.0.0.0/localhost/' | sed -e 's/tkeir_shell/localhost/'`; done
