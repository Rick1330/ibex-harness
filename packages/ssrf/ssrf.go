// Package ssrf provides shared destination checks for outbound URLs (F4-018).
// Predicates mirror services/api/app/services/provider_validate_net.py.
package ssrf

import (
	"context"
	"crypto/tls"
	"errors"
	"fmt"
	"net"
	"net/http"
	"net/url"
	"strings"
	"time"
)

var (
	// ErrBlockedDestination is returned when a URL host resolves to a non-public address.
	ErrBlockedDestination = errors.New("ssrf: blocked destination")
	// ErrInvalidURL is returned for empty, non-http(s), or unparsable URLs.
	ErrInvalidURL = errors.New("ssrf: invalid url")
)

// IsBlockedIP reports whether addr is unsuitable for outbound provider dials.
func IsBlockedIP(ip net.IP) bool {
	if ip == nil {
		return true
	}
	if ip4 := ip.To4(); ip4 != nil {
		ip = ip4
	}
	return ip.IsPrivate() ||
		ip.IsLoopback() ||
		ip.IsLinkLocalUnicast() ||
		ip.IsLinkLocalMulticast() ||
		ip.IsMulticast() ||
		ip.IsUnspecified() ||
		isCGNAT(ip) ||
		isDocumentation(ip)
}

func isCGNAT(ip net.IP) bool {
	ip4 := ip.To4()
	if ip4 == nil {
		return false
	}
	// 100.64.0.0/10 (RFC 6598)
	return ip4[0] == 100 && ip4[1] >= 64 && ip4[1] <= 127
}

func isDocumentation(ip net.IP) bool {
	ip4 := ip.To4()
	if ip4 == nil {
		return false
	}
	// 192.0.2.0/24, 198.51.100.0/24, 203.0.113.0/24
	if ip4[0] == 192 && ip4[1] == 0 && ip4[2] == 2 {
		return true
	}
	if ip4[0] == 198 && ip4[1] == 51 && ip4[2] == 100 {
		return true
	}
	if ip4[0] == 203 && ip4[1] == 0 && ip4[2] == 113 {
		return true
	}
	return false
}

// ValidateHTTPURL parses raw, requires http/https, resolves the host, and rejects
// if any resolved address is blocked. empty raw is allowed (no custom base URL).
func ValidateHTTPURL(ctx context.Context, raw string) error {
	_, err := validateHTTPURLParts(ctx, raw)
	return err
}

type urlParts struct {
	u          *url.URL
	serverName string
	connectIP  string
}

func validateHTTPURLParts(ctx context.Context, raw string) (urlParts, error) {
	raw = strings.TrimSpace(raw)
	if raw == "" {
		return urlParts{}, nil
	}
	u, err := url.Parse(raw)
	if err != nil || u.Host == "" {
		return urlParts{}, ErrInvalidURL
	}
	scheme := strings.ToLower(u.Scheme)
	if scheme != "http" && scheme != "https" {
		return urlParts{}, ErrInvalidURL
	}
	serverName := u.Hostname()
	if serverName == "" {
		return urlParts{}, ErrInvalidURL
	}
	connectIP, err := resolvePublicConnectIP(ctx, serverName)
	if err != nil {
		return urlParts{}, err
	}
	return urlParts{u: u, serverName: serverName, connectIP: connectIP}, nil
}

func resolvePublicConnectIP(ctx context.Context, host string) (string, error) {
	if lit := net.ParseIP(host); lit != nil {
		if IsBlockedIP(lit) {
			return "", ErrBlockedDestination
		}
		return lit.String(), nil
	}
	addrs, err := net.DefaultResolver.LookupIPAddr(ctx, host)
	if err != nil || len(addrs) == 0 {
		return "", ErrBlockedDestination
	}
	for _, a := range addrs {
		if IsBlockedIP(a.IP) {
			return "", ErrBlockedDestination
		}
	}
	return addrs[0].IP.String(), nil
}

// PinResult is a validated dial target: connect via ConnectHost, TLS/SNI via ServerName.
type PinResult struct {
	PinnedURL  string
	ServerName string
	ConnectIP  string
}

// ValidateAndPinHTTPURL validates then rewrites the URL host to the first safe IP.
func ValidateAndPinHTTPURL(ctx context.Context, raw string) (PinResult, error) {
	parts, err := validateHTTPURLParts(ctx, raw)
	if err != nil || parts.u == nil {
		return PinResult{}, err
	}
	hostPort := parts.connectIP
	if strings.Contains(parts.connectIP, ":") {
		hostPort = "[" + parts.connectIP + "]"
	}
	if port := parts.u.Port(); port != "" {
		hostPort = net.JoinHostPort(parts.connectIP, port)
	}
	parts.u.Host = hostPort
	return PinResult{
		PinnedURL:  parts.u.String(),
		ServerName: parts.serverName,
		ConnectIP:  parts.connectIP,
	}, nil
}

// SafeDialContext resolves addr, rejects blocked IPs, and dials the first safe address.
func SafeDialContext(ctx context.Context, network, addr string) (net.Conn, error) {
	host, port, err := net.SplitHostPort(addr)
	if err != nil {
		return nil, fmt.Errorf("%w: %v", ErrInvalidURL, err)
	}
	if lit := net.ParseIP(host); lit != nil {
		if IsBlockedIP(lit) {
			return nil, ErrBlockedDestination
		}
		var d net.Dialer
		return d.DialContext(ctx, network, addr)
	}
	addrs, err := net.DefaultResolver.LookupIPAddr(ctx, host)
	if err != nil || len(addrs) == 0 {
		return nil, ErrBlockedDestination
	}
	var d net.Dialer
	var last error
	for _, a := range addrs {
		if IsBlockedIP(a.IP) {
			last = ErrBlockedDestination
			continue
		}
		target := net.JoinHostPort(a.IP.String(), port)
		conn, err := d.DialContext(ctx, network, target)
		if err == nil {
			return conn, nil
		}
		last = err
	}
	if last == nil {
		last = ErrBlockedDestination
	}
	return nil, last
}

// WrapTransport clones t (or uses a default) with SafeDialContext.
func WrapTransport(base http.RoundTripper) *http.Transport {
	var t *http.Transport
	if bt, ok := base.(*http.Transport); ok && bt != nil {
		t = bt.Clone()
	} else {
		t = http.DefaultTransport.(*http.Transport).Clone()
	}
	t.DialContext = SafeDialContext
	t.DialTLSContext = nil
	return t
}

// ClientWithSafeDial returns a shallow client copy whose Transport uses SafeDialContext.
func ClientWithSafeDial(base *http.Client) *http.Client {
	return ClientForPinnedDial(base, "")
}

// ClientForPinnedDial returns a client that dials via SafeDialContext and, when
// serverName is set, presents that name for TLS SNI (IP-literal BaseURL pin).
func ClientForPinnedDial(base *http.Client, serverName string) *http.Client {
	if base == nil {
		base = &http.Client{Timeout: 30 * time.Second}
	}
	out := *base
	t := WrapTransport(base.Transport)
	if serverName != "" {
		if t.TLSClientConfig == nil {
			t.TLSClientConfig = &tls.Config{MinVersion: tls.VersionTLS12}
		} else {
			t.TLSClientConfig = t.TLSClientConfig.Clone()
		}
		t.TLSClientConfig.ServerName = serverName
	}
	out.Transport = t
	return &out
}
