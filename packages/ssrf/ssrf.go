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

// lookupIPAddr resolves hostnames; tests may replace it via SetLookupIPAddrForTest.
var lookupIPAddr = func(ctx context.Context, host string) ([]net.IPAddr, error) {
	return net.DefaultResolver.LookupIPAddr(ctx, host)
}

// SetLookupIPAddrForTest replaces hostname resolution (tests only). Restore via cleanup.
func SetLookupIPAddrForTest(fn func(context.Context, string) ([]net.IPAddr, error)) func() {
	prev := lookupIPAddr
	if fn == nil {
		lookupIPAddr = func(ctx context.Context, host string) ([]net.IPAddr, error) {
			return net.DefaultResolver.LookupIPAddr(ctx, host)
		}
	} else {
		lookupIPAddr = fn
	}
	return func() { lookupIPAddr = prev }
}

// IsBlockedIP reports whether addr is unsuitable for outbound provider dials.
func IsBlockedIP(ip net.IP) bool {
	if ip == nil {
		return true
	}
	if ip4 := ip.To4(); ip4 != nil {
		return isBlockedIPv4(ip4)
	}
	return isBlockedIPv6(ip)
}

func isBlockedIPv4(ip net.IP) bool {
	if isNetBlocked(ip) {
		return true
	}
	return isSpecialUseIPv4(ip)
}

func isBlockedIPv6(ip net.IP) bool {
	if isNetBlocked(ip) {
		return true
	}
	return isIPv6Documentation(ip)
}

func isNetBlocked(ip net.IP) bool {
	if ip.IsPrivate() {
		return true
	}
	if ip.IsLoopback() {
		return true
	}
	if ip.IsLinkLocalUnicast() {
		return true
	}
	if ip.IsLinkLocalMulticast() {
		return true
	}
	if ip.IsMulticast() {
		return true
	}
	return ip.IsUnspecified()
}

func isSpecialUseIPv4(ip net.IP) bool {
	if isCGNAT(ip) {
		return true
	}
	if isDocumentation(ip) {
		return true
	}
	if isBenchmarking(ip) {
		return true
	}
	return isBroadcast(ip)
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
	if matchIPv4Prefix24(ip4, 192, 0, 2) {
		return true
	}
	if matchIPv4Prefix24(ip4, 198, 51, 100) {
		return true
	}
	return matchIPv4Prefix24(ip4, 203, 0, 113)
}

func matchIPv4Prefix24(ip4 net.IP, a, b, c byte) bool {
	return ip4[0] == a && ip4[1] == b && ip4[2] == c
}

func isBenchmarking(ip net.IP) bool {
	ip4 := ip.To4()
	if ip4 == nil {
		return false
	}
	// 198.18.0.0/15 (RFC 2544)
	return ip4[0] == 198 && (ip4[1] == 18 || ip4[1] == 19)
}

func isBroadcast(ip net.IP) bool {
	ip4 := ip.To4()
	if ip4 == nil {
		return false
	}
	return ip4[0] == 255 && ip4[1] == 255 && ip4[2] == 255 && ip4[3] == 255
}

func isIPv6Documentation(ip net.IP) bool {
	if ip.To4() != nil {
		return false
	}
	if len(ip) != net.IPv6len {
		return false
	}
	// 2001:db8::/32 (RFC 3849)
	return ip[0] == 0x20 && ip[1] == 0x01 && ip[2] == 0x0d && ip[3] == 0xb8
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
	// Provider BaseURL must be https; empty raw (platform default) is allowed above.
	if scheme != "https" {
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
		return connectIPFromLiteral(lit)
	}
	return connectIPFromLookup(ctx, host)
}

func connectIPFromLiteral(lit net.IP) (string, error) {
	if IsBlockedIP(lit) {
		return "", ErrBlockedDestination
	}
	return lit.String(), nil
}

func connectIPFromLookup(ctx context.Context, host string) (string, error) {
	addrs, err := lookupIPAddr(ctx, host)
	if err != nil || len(addrs) == 0 {
		return "", ErrBlockedDestination
	}
	if err := rejectBlockedAddrs(addrs); err != nil {
		return "", err
	}
	return addrs[0].IP.String(), nil
}

func rejectBlockedAddrs(addrs []net.IPAddr) error {
	for _, a := range addrs {
		if IsBlockedIP(a.IP) {
			return ErrBlockedDestination
		}
	}
	return nil
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

// dialTarget groups SafeDialContext resolution inputs.
type dialTarget struct {
	network string
	host    string
	port    string
	addr    string // original host:port when dialing a literal
}

// SafeDialContext resolves addr, rejects blocked IPs, and dials the first safe address.
func SafeDialContext(ctx context.Context, network, addr string) (net.Conn, error) {
	host, port, err := net.SplitHostPort(addr)
	if err != nil {
		return nil, fmt.Errorf("%w: %v", ErrInvalidURL, err)
	}
	target := dialTarget{network: network, host: host, port: port, addr: addr}
	if lit := net.ParseIP(host); lit != nil {
		return dialLiteralIP(ctx, target, lit)
	}
	return dialResolvedHosts(ctx, target)
}

func dialLiteralIP(ctx context.Context, target dialTarget, lit net.IP) (net.Conn, error) {
	if IsBlockedIP(lit) {
		return nil, ErrBlockedDestination
	}
	var d net.Dialer
	return d.DialContext(ctx, target.network, target.addr)
}

func dialResolvedHosts(ctx context.Context, target dialTarget) (net.Conn, error) {
	addrs, err := lookupIPAddr(ctx, target.host)
	if err != nil || len(addrs) == 0 {
		return nil, ErrBlockedDestination
	}
	var d net.Dialer
	var last error
	for _, a := range addrs {
		conn, err := dialOneResolved(ctx, &d, target, a.IP)
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

func dialOneResolved(ctx context.Context, d *net.Dialer, target dialTarget, ip net.IP) (net.Conn, error) {
	if IsBlockedIP(ip) {
		return nil, ErrBlockedDestination
	}
	return d.DialContext(ctx, target.network, net.JoinHostPort(ip.String(), target.port))
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
// Redirects are restricted to the original pinned host so credentials are not
// forwarded cross-host.
func ClientForPinnedDial(base *http.Client, serverName string) *http.Client {
	if base == nil {
		base = &http.Client{Timeout: 30 * time.Second}
	}
	out := *base
	t := WrapTransport(base.Transport)
	if serverName != "" {
		applyPinnedTLS(t, serverName)
		out.CheckRedirect = pinnedHTTPSRedirect(strings.ToLower(serverName))
	}
	out.Transport = t
	return &out
}

func applyPinnedTLS(t *http.Transport, serverName string) {
	if t.TLSClientConfig == nil {
		t.TLSClientConfig = &tls.Config{MinVersion: tls.VersionTLS12}
	} else {
		t.TLSClientConfig = t.TLSClientConfig.Clone()
	}
	t.TLSClientConfig.ServerName = serverName
}

// pinnedHTTPSRedirect rejects cross-host and non-HTTPS redirects for pinned dials.
func pinnedHTTPSRedirect(pinnedHost string) func(*http.Request, []*http.Request) error {
	return func(req *http.Request, via []*http.Request) error {
		if len(via) >= 10 {
			return errors.New("ssrf: too many redirects")
		}
		if strings.ToLower(req.URL.Scheme) != "https" {
			return fmt.Errorf("%w: redirect scheme must be https", ErrBlockedDestination)
		}
		if strings.ToLower(req.URL.Hostname()) != pinnedHost {
			return fmt.Errorf("%w: redirect host %q != pinned %q", ErrBlockedDestination, req.URL.Hostname(), pinnedHost)
		}
		return nil
	}
}
