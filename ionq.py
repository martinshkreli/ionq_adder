from qiskit import QuantumCircuit, QuantumRegister, ClassicalRegister, transpile
from qiskit.circuit.library import CDKMRippleCarryAdder
from qiskit_braket_provider import AWSBraketBackend
from braket.aws import AwsDevice
import random
import os

def run_on_aws_braket(a, b, device_arn="", shots=1000):
    k = max(a.bit_length(), b.bit_length(), (a+b).bit_length())
    print(f"Computing {a} + {b}")
    print(f"Bit width: {k} bits (sum needs {(a+b).bit_length()} bits)")

    qc = QuantumCircuit(QuantumRegister(1, 'cin'), QuantumRegister(k, 'a'),
                        QuantumRegister(k, 'b'), QuantumRegister(1, 'cout'),
                        ClassicalRegister(2*k+2, 'res'))

    for i in range(k):
        if (a >> i) & 1: qc.x(qc.qregs[1][i])
        if (b >> i) & 1: qc.x(qc.qregs[2][i])

    qc.append(CDKMRippleCarryAdder(k, 'full'), qc.qubits)

    for i in range(k): qc.measure(qc.qregs[2][i], qc.cregs[0][i])
    qc.measure(qc.qregs[3][0], qc.cregs[0][k])

    print(f"Circuit uses {qc.num_qubits} qubits")
    print(f"Circuit depth: {qc.depth()}")

    print(f"\nConnecting to device: {device_arn.split('/')[-1]}")

    device = AwsDevice(device_arn)
    backend = AWSBraketBackend(device=device)

    print("Transpiling circuit for backend...")
    transpiled_qc = transpile(qc, backend=backend, optimization_level=1)
    print(f"Transpiled circuit depth: {transpiled_qc.depth()}")

    print(f"Submitting job with {shots} shots...")
    job = backend.run(transpiled_qc, shots=shots)
    print(f"Job ID: {job.job_id()}")
    print("Waiting for results...")

    result = job.result()
    counts = result.get_counts()

    most_common = max(counts, key=counts.get)
    quantum_sum = int(most_common, 2)

    print(f"\n=== Results ===")
    print(f"Classical sum: {a + b}")
    print(f"Quantum sum: {quantum_sum} ({'✓' if quantum_sum == a+b else '✗'})")
    print(f"Confidence: {counts[most_common]}/{shots} = {counts[most_common]/shots:.1%}")
    print(f"Unique outcomes: {len(counts)} (noise: {'yes' if len(counts) > 1 else 'no'})")

    if len(counts) > 5:
        print("\nTop 5 outcomes:")
        sorted_counts = sorted(counts.items(), key=lambda x: x[1], reverse=True)[:5]
        for bitstring, count in sorted_counts:
            decimal = int(bitstring, 2)
            error = abs(decimal - (a+b))
            print(f"  {decimal:4d} (error: {error:3d}): {count:3d} times")

    return quantum_sum, result

# Main execution
if __name__ == "__main__":
    a = random.randint(1024, 4096)
    b = random.randint(1024, 4096)
    device_arn = "arn:aws:braket:us-east-1::device/qpu/ionq/Forte-Enterprise-1"
    quantum_sum, result = run_on_aws_braket(a, b, device_arn=device_arn, shots=1000)
