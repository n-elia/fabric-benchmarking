package chaincode

import (
	"fmt"
	"math"
	"time"
)

func computeSignalEnergy(in []float64) float64 {
	var energy float64
	energy = 0

	for _, val := range in {
		energy += math.Pow(math.Abs(val), 2)
	}

	return energy
}

func computeSignalMeanEnergy(in []float64) float64 {
	return computeSignalEnergy(in) / float64(len(in))
}

// =========== available policies map ===========
var AvailablePolicies = map[string]Policy{
	examplePolicy.Id: examplePolicy,
	energyPolicy.Id:  energyPolicy,
}

func getAvailablePolicies() (count int, msg string) {
	pol := []string{}
	for _, element := range AvailablePolicies {
		pol = append(pol, fmt.Sprint(element))
	}
	count = len(pol)

	if count == 0 {
		msg = fmt.Sprint("No available policies.")
		return
	}

	msg = fmt.Sprint("List of available policies:", pol)
	return
}

func getPolicy(id string) (*Policy, error) {
	p, ok := AvailablePolicies[id]
	if !ok {
		return &Policy{}, fmt.Errorf("Policy with id %q is not allowed.", id)
	}
	return &p, nil
}

func ApplyPolicy(policyId string, d ChunkData) (time.Duration, error) {
	p, err := getPolicy(policyId)
	if err != nil {
		return time.Duration(0), fmt.Errorf("Policy not found: %s", err)
	}

	return p.applyToChunkData(d)
}

// =========== policy interface ===========
type PolicyInterface interface {
	applyToChunkData(d ChunkData) (time.Duration, error)
	getDescription() string
	getPolicyId() string
}

type Policy struct {
	Id          string
	Description string
	Logic       func(d ChunkData) (time.Duration, error)
}

func (p *Policy) applyToChunkData(d ChunkData) (time.Duration, error) {
	return p.Logic(d)
}

func (p *Policy) getDescription() string {
	return p.Description
}

func (p *Policy) getPolicyId() string {
	return p.Id
}

func (p Policy) String() string {
	return fmt.Sprintf("Policy with Id %q and description %q.", p.Id, p.Description)
}

// =========== Policy 1 - example policy ===========
func examplePolicyLogic(d ChunkData) (time.Duration, error) {
	expiryTimeString := "24h"
	if time.Now().Second()%2 == 0 {
		expiryTimeString = "48h"
	}
	expiryTimeDuration, err := time.ParseDuration(expiryTimeString)
	if err != nil {
		return time.Duration(0), err
	}
	return expiryTimeDuration, nil
}

var examplePolicy = Policy{
	Id:          "example_policy_v1",
	Description: "This is a sample policy.",
	Logic:       examplePolicyLogic,
}

// =========== Policy 2 - mean energy policy ===========
type Threshold struct {
	X float64
	Y float64
	Z float64
}

func energyPolicyLogic(d ChunkData) (time.Duration, error) {
	thr := Threshold{
		X: 1.8191607053598602e-06,
		Y: 1.2442575637320148e-06,
		Z: 1.0956301130461567e-06,
	}

	// defaultExpiryTimeString := "24h"
	// thrExpiryTimeString := "8760h" // 365 days
	defaultExpiryTimeString := "31800ms"
	thrExpiryTimeString := "127200ms"

	var energyArray [18]float64

	energyArray[0] = computeSignalMeanEnergy(d.Sensor0.X)
	energyArray[1] = computeSignalMeanEnergy(d.Sensor0.Y)
	energyArray[2] = computeSignalMeanEnergy(d.Sensor0.Z)

	energyArray[3] = computeSignalMeanEnergy(d.Sensor1.X)
	energyArray[4] = computeSignalMeanEnergy(d.Sensor1.Y)
	energyArray[5] = computeSignalMeanEnergy(d.Sensor1.Z)

	energyArray[6] = computeSignalMeanEnergy(d.Sensor2.X)
	energyArray[7] = computeSignalMeanEnergy(d.Sensor2.Y)
	energyArray[8] = computeSignalMeanEnergy(d.Sensor2.Z)

	energyArray[9] = computeSignalMeanEnergy(d.Sensor3.X)
	energyArray[10] = computeSignalMeanEnergy(d.Sensor3.Y)
	energyArray[11] = computeSignalMeanEnergy(d.Sensor3.Z)

	energyArray[12] = computeSignalMeanEnergy(d.Sensor4.X)
	energyArray[13] = computeSignalMeanEnergy(d.Sensor4.Y)
	energyArray[14] = computeSignalMeanEnergy(d.Sensor4.Z)

	energyArray[15] = computeSignalMeanEnergy(d.Sensor5.X)
	energyArray[16] = computeSignalMeanEnergy(d.Sensor5.Y)
	energyArray[17] = computeSignalMeanEnergy(d.Sensor5.Z)

	expiryTimeString := defaultExpiryTimeString
	j := 0
	for _, val := range energyArray {
		if ((j == 0) && (val > thr.X)) ||
			((j == 1) && (val > thr.Y)) ||
			((j == 2) && (val > thr.Z)) {
			expiryTimeString = thrExpiryTimeString
		}

		j += 1

		if j == 3 {
			j = 0
		}
	}

	expiryTimeDuration, err := time.ParseDuration(expiryTimeString)
	if err != nil {
		return time.Duration(0), err
	}

	return expiryTimeDuration, nil
}

var energyPolicy = Policy{
	Id: "signal_energy_policy_v1",
	Description: `This policy computes the average signal energy, and ` +
		`establishes an expiry time duration based on a threshold.`,
	Logic: energyPolicyLogic,
}
