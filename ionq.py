from qiskit import QuantumCircuit, QuantumRegister, ClassicalRegister, transpile
from qiskit.circuit.library import CDKMRippleCarryAdder
from qiskit_braket_provider import AWSBraketBackend
from braket.aws import AwsDevice
import random
import os

def run_on_aws_braket(a, b, device_arn="", shots=100):
    k = max(a.bit_length(), b.bit_length())
    print(f"Computing {a} + {b}")
    print(f"Bit width: {k} bits (sum needs {(a+b).bit_length()} bits)")
    
    # Half mode: 2*k + 2 qubits (a, b, cout, and 1 ancilla)
    qc = QuantumCircuit(QuantumRegister(k, 'a'),
                        QuantumRegister(k, 'b'),
                        QuantumRegister(1, 'cout'),
                        QuantumRegister(1, 'ancilla'),
                        ClassicalRegister(2*k+2, 'res'))
    
    # Initialize inputs
    for i in range(k):
        if (a >> i) & 1: qc.x(qc.qregs[0][i])
        if (b >> i) & 1: qc.x(qc.qregs[1][i])
    
    # Use 'half' mode (no cin, but has cout for overflow)
    qc.append(CDKMRippleCarryAdder(k, 'half'), qc.qubits)
    
    # Measure result bits (b register contains the sum)
    for i in range(k): 
        qc.measure(qc.qregs[1][i], qc.cregs[0][i])
    
    # Measure cout (overflow bit)
    qc.measure(qc.qregs[2][0], qc.cregs[0][k])
    
    # Measure ancilla
    qc.measure(qc.qregs[3][0], qc.cregs[0][k+1])
    
    # Measure remaining qubits (a register)
    for i in range(k): 
        qc.measure(qc.qregs[0][i], qc.cregs[0][k+2+i])
    
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
    
    # Extract the first k+1 bits (k bits for sum + 1 bit for overflow)
    result_counts = {}
    for bitstring, count in counts.items():
        result_bits = bitstring[-(k+1):]  # Last k+1 bits: sum + cout
        result_counts[result_bits] = result_counts.get(result_bits, 0) + count
    
    most_common = max(result_counts, key=result_counts.get)
    quantum_sum = int(most_common, 2)
    
    # Check overflow
    overflow_bit = int(most_common[0])  # First bit is cout
    sum_value = int(most_common[1:], 2)  # Remaining bits are the sum
    
    print(f"\n=== Results ===")
    print(f"Classical sum: {a + b}")
    print(f"Quantum sum: {quantum_sum} ({'✓' if quantum_sum == a+b else '✗'})")
    print(f"Overflow detected: {'YES' if overflow_bit else 'NO'} (cout={overflow_bit})")
    print(f"Sum value (without overflow): {sum_value}")
    print(f"Confidence: {result_counts[most_common]}/{shots} = {result_counts[most_common]/shots:.1%}")
    print(f"Unique outcomes: {len(result_counts)} (noise: {'yes' if len(result_counts) > 1 else 'no'})")
    
    if len(result_counts) > 5:
        print("\nTop 5 outcomes:")
        sorted_counts = sorted(result_counts.items(), key=lambda x: x[1], reverse=True)[:5]
        for bitstring, count in sorted_counts:
            decimal = int(bitstring, 2)
            overflow = int(bitstring[0])
            error = abs(decimal - (a+b))
            print(f"  {decimal:4d} (overflow={overflow}, error: {error:3d}): {count:3d} times")
    
    return quantum_sum, result

# Main execution
if __name__ == "__main__":
    a = random.randint(100000, 131072)
    b = random.randint(100000, 131072)
    device_arn = "arn:aws:braket:us-east-1::device/qpu/ionq/Forte-Enterprise-1"
    quantum_sum, result = run_on_aws_braket(a, b, device_arn=device_arn, shots=100)
