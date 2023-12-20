package chaincode

import (
	"crypto/md5"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"strings"
)

func base64DecodeJson(v interface{}, enc string) error {
	return json.NewDecoder(base64.NewDecoder(base64.StdEncoding, strings.NewReader(enc))).Decode(v)
}

// md5 hash calculator
func md5Hash(data string) (string, error) {
	hmd5 := md5.Sum([]byte(data))
	return fmt.Sprintf("%x", hmd5), nil
}
