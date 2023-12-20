package chaincode

import (
	"encoding/json"
	"fmt"
	"time"
)

// Data structures for unmarshaling JSON messages
type SensorData struct {
	X []float64 `json:"x"`
	Y []float64 `json:"y"`
	Z []float64 `json:"z"`
}

type ChunkData struct {
	Id      string     `json:"id"`
	Sensor0 SensorData `json:"0"`
	Sensor1 SensorData `json:"1"`
	Sensor2 SensorData `json:"2"`
	Sensor3 SensorData `json:"3"`
	Sensor4 SensorData `json:"4"`
	Sensor5 SensorData `json:"5"`
}

func (d *ChunkData) hash() (string, error) {
	// serialize to JSON
	dataJSON, err := json.Marshal(d)
	if err != nil {
		return "", fmt.Errorf("unable to serialize to JSON: %s", err)
	}

	// compute md5 hash
	dataHash, err := md5Hash(string(dataJSON))
	if err != nil {
		return "", fmt.Errorf("unable to compute data hash: %s", err)
	}

	return dataHash, nil
}

func (d *ChunkData) applyPolicy(p PolicyInterface) (time.Duration, error) {
	return p.applyToChunkData(*d)
}

func (d *ChunkData) applyPolicyById(policyId string) (time.Duration, error) {
	p, err := getPolicy(policyId)
	if err != nil {
		return time.Duration(0), fmt.Errorf("unable to find policy: %s", err)
	}

	return p.applyToChunkData(*d)
}
