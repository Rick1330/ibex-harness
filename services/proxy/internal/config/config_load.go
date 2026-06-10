package config

import (
	"net"
)

func Load() (Config, error) {
	return loadFromEnv()
}

func ListenAddress(port string) string {
	return net.JoinHostPort("", port)
}
