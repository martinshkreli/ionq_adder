# Forte-Enterprise-1 friendly adder with a separate SUM register (correct logic)
# Qubits used: ~4k + 1 (a[k] + b[k] + c[k+1] + s[k])

from braket.aws import AwsDevice, AwsSession
from braket.circuits import Circuit
from collections import Counter

# --- Helpers ---
def int_to_bits_le(x: int, width: int):
    return [(x >> i) & 1 for i in range(width)]

def ccx_decomposed(circ: Circuit, a: int, b: int, t: int) -> Circuit:
    """
    Toffoli (CCX) using only {H,S,Si,T,Ti,CNOT}.
    Controls: a, b ; target: t
    """
    circ.h(t)
    circ.cnot(b, t);  circ.ti(t)
    circ.cnot(a, t);  circ.t(t)
    circ.cnot(b, t);  circ.ti(t)
    circ.cnot(a, t);  circ.t(b);  circ.t(t)
    circ.h(t)
    circ.cnot(a, b);  circ.t(a);  circ.si(b);  circ.cnot(a, b)
    return circ

def full_adder(a: int, b: int, cin: int, s: int, cout: int) -> Circuit:
    """
    Full adder with SEPARATE sum qubit `s`:
      s   ^= a
      s   ^= b                 # s = a XOR b
      cout ^= a & b
      cout ^= cin & s          # uses s = (a XOR b)
      s   ^= cin               # s = a XOR b XOR cin
    """
    c = Circuit()
    c.cnot(a, s)
    c.cnot(b, s)
    ccx_decomposed(c, a, b, cout)
    ccx_decomposed(c, cin, s, cout)
    c.cnot(cin, s)
    return c

def build_adder_circuit(a_val: int, b_val: int):
    if a_val < 0 or b_val < 0:
        raise ValueError("Only non-negative integers are supported.")
    k = max(1, max(a_val.bit_length(), b_val.bit_length()))

    # Layout (contiguous):
    #   a[0..k-1], b[0..k-1], c[0..k], s[0..k-1]
    a_off = 0
    b_off = a_off + k
    c_off = b_off + k
    s_off = c_off + (k + 1)

    a_idx = [a_off + i for i in range(k)]
    b_idx = [b_off + i for i in range(k)]
    c_idx = [c_off + i for i in range(k + 1)]
    s_idx = [s_off + i for i in range(k)]

    circ = Circuit()

    # Initialize |a>, |b| (little-endian within registers)
    for i, bit in enumerate(int_to_bits_le(a_val, k)):
        if bit: circ.x(a_idx[i])
    for i, bit in enumerate(int_to_bits_le(b_val, k)):
        if bit: circ.x(b_idx[i])

    # k stages
    for i in range(k):
        circ += full_adder(a_idx[i], b_idx[i], c_idx[i], s_idx[i], c_idx[i+1])

    # --- Forte requires ALL used qubits be measured ---
    # Order: a, b, c, s (so decoding is straightforward)
    measure_order = a_idx + b_idx + c_idx + s_idx
    for q in measure_order:
        circ.measure(q)

    meta = {"k": k, "a": a_idx, "b": b_idx, "c": c_idx, "s": s_idx, "measure_order": measure_order}
    return circ, meta

def decode_sum(counts: Counter, measured_qubits: list[int], meta: dict) -> int:
    """
    Choose the most frequent outcome; map bits onto qubits;
    extract SUM from s[0..k-1] and final carry c[k].
    Braket bitstrings align left-to-right with measured_qubits order.
    """
    if not counts:
        raise RuntimeError("No counts returned.")
    bitstr, _ = max(counts.items(), key=lambda kv: kv[1])
    bits_by_q = {measured_qubits[i]: int(bitstr[i]) for i in range(len(measured_qubits))}
    k = meta["k"]
    # sum = Σ s[i] << i  +  (carry << k)
    sum_low = 0
    for i, q in enumerate(meta["s"]):
        sum_low |= bits_by_q[q] << i
    carry = bits_by_q[meta["c"][-1]]
    return sum_low + (carry << k)

def run_ionq_adder(
    a: int,
    b: int,
    device_arn: str = "arn:aws:braket:us-east-1::device/qpu/ionq/Forte-Enterprise-1",
    shots: int = 1000,
    s3_bucket: str | None = None,
    s3_prefix: str = "ionq-adder/results",
):
    k = max(1, max(a.bit_length(), b.bit_length()))
    qubits_needed = 4 * k + 1
    print(f"Inputs: a={a}, b={b} | k={k} | qubits ≈ {qubits_needed}")

    circ, meta = build_adder_circuit(a, b)

    aws_sess = AwsSession()
    bucket = s3_bucket or aws_sess.default_bucket()
    s3_folder = (bucket, s3_prefix)

    device = AwsDevice(device_arn)
    print(f"Submitting to {device_arn} | shots={shots} | s3://{bucket}/{s3_prefix}")
    task = device.run(circ, shots=shots, s3_destination_folder=s3_folder)
    print("Task ID:", task.id, "(waiting...)")
    result = task.result()

    print("\n=== Raw ===")
    print("measured_qubits:", result.measured_qubits)
    print("counts:", result.measurement_counts)

    qsum = decode_sum(result.measurement_counts, result.measured_qubits, meta)
    print("\n=== Decoded ===")
    print(f"quantum sum = {qsum} | classical sum = {a + b}")
    print("MATCH" if qsum == a + b else "MISMATCH")
    return qsum, result

a, b = 553, 452
qsum, res = run_ionq_adder(a, b)
