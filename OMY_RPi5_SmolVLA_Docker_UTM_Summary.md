# OMY Raspberry Pi 5에서 SmolVLA 직접 Inference 구성 정리

## 1. 목표

OMY 내부의 **Raspberry Pi 5**에서 서버 없이 직접 SmolVLA를 실행해 실제 OMY를 제어하는 것이 목표다.

최종 목표 구조:

```text
OMY Raspberry Pi 5
└─ Cyclo OS
   ├─ 기존 OMY bringup
   ├─ 기존 camera node
   └─ smolvla_rpi Docker
      ├─ Python
      ├─ PyTorch ARM64 CPU
      ├─ LeRobot
      ├─ SmolVLA
      ├─ 훈련/양자화 모델
      └─ smolvla_inference_node
```

---

## 2. Cyclo Intelligence는 필수인가?

아니다.

ROBOTIS의 Cyclo Intelligence를 사용하면 모델 선택, observation 수집, inference, action 전달 등을 이미 만들어진 구조에서 사용할 수 있다.

하지만 **훈련된 SmolVLA 모델을 LeRobot에서 직접 불러와 inference하는 것도 가능**하다.

따라서 Raspberry Pi 5 경량화 프로젝트에서는 Cyclo 전체를 포팅하기보다 다음과 같이 직접 구성하는 방법이 더 단순할 수 있다.

```text
Camera ───────────────┐
                      │
/joint_states ────────┼──> smolvla_inference_node
                      │          │
Language instruction ─┘          │
                                 ▼
                              SmolVLA
                                 │
                                 ▼
                           action command
                                 │
                                 ▼
                         OMY controller
                                 │
                                 ▼
                               OMY
```

---

## 3. 필요한 실행 코드 / 노드

기본적으로 세 부분만 있으면 된다.

### ① OMY Bringup

기존 ROBOTIS bringup 코드를 사용한다.

역할:

- Dynamixel / OMY hardware 연결
- `ros2_control` 실행
- `/joint_states` 발행
- arm controller 실행
- VLA가 생성한 action command 수신

즉 새로 만들 필요 없이 기존 OMY 코드를 사용한다.

---

### ② Camera Node

기존 카메라 드라이버를 사용한다.

예:

```text
/cam_wrist/color/image_raw
```

역할:

- 카메라 영상 획득
- ROS2 image topic 발행

SmolVLA 학습 시 사용했던 카메라 구성과 inference 시 입력 구성이 일치해야 한다.

---

### ③ SmolVLA Inference Node

새로 만들어야 하는 핵심 코드다.

예:

```text
smolvla_inference_node.py
```

역할:

1. `/joint_states` 구독
2. 카메라 image topic 구독
3. 자연어 task instruction 입력
4. SmolVLA 모델 load
5. LeRobot preprocessor 실행
6. SmolVLA inference
7. action 생성
8. OMY controller로 ROS2 command publish

전체 흐름:

```text
/joint_states ─────────────┐
                           │
/camera/image_raw ─────────┼──> SmolVLA inference node
                           │
"pick up the red block" ───┘
                               │
                               ▼
                         LeRobot preprocess
                               │
                               ▼
                            SmolVLA
                               │
                               ▼
                           action chunk
                               │
                               ▼
                         ROS2 command
                               │
                               ▼
                        OMY ros2_control
```

---

## 4. 언어 instruction 전달 방법

SmolVLA는 다음 세 종류의 입력을 사용한다.

```text
Camera image
+
Robot state
+
Natural language instruction
```

예:

```text
"pick up the red block"
```

직접 token ID를 만들어 넣을 필요는 없다.

문자열을 inference node에서 전달하면 LeRobot의 preprocessor/tokenizer가 SmolVLA용 language token으로 변환한다.

초기에는 ROS parameter로 전달 가능하다.

예:

```bash
ros2 run omy_smolvla smolvla_inference_node \
  --ros-args \
  -p task:="pick up the red block"
```

추후 명령을 실시간으로 변경하고 싶다면:

```text
/smolvla/task
```

같은 `std_msgs/String` ROS2 topic을 만들어도 된다.

---

## 5. Cyclo 없이 SmolVLA를 실행할 때 필요한 환경

훈련된 모델 파일만 복사한다고 바로 실행되는 것은 아니다.

SmolVLA 구조와 preprocessing을 처리하는 **LeRobot 환경**이 필요하다.

필요한 최소 구성:

```text
ARM64 Linux
Python
PyTorch CPU
torchvision
LeRobot
SmolVLA dependencies
ROS2 Jazzy Python 환경
훈련된 SmolVLA checkpoint
smolvla_inference_node.py
```

핵심 설치 요소:

```text
PyTorch ARM64 CPU
+
LeRobot
+
SmolVLA
```

LeRobot을 통해 다음과 같이 모델을 직접 불러오는 구조가 된다.

```python
policy = SmolVLAPolicy.from_pretrained(
    "/models/my_smolvla"
)
```

---

## 6. Docker를 사용하는 이유

Docker를 사용해도 실제 inference 연산은 **Raspberry Pi 5 CPU**가 수행한다.

Docker는 성능을 대신 만들어주는 것이 아니라:

- 패키지 격리
- 버전 고정
- 환경 재현
- OMY 기본 OS 보호
- 다른 장치로 동일 환경 배포

를 위해 사용한다.

최종적으로 만들 Docker:

```text
smolvla_rpi
├─ ARM64 Linux
├─ Python
├─ PyTorch ARM64 CPU
├─ torchvision
├─ LeRobot
├─ SmolVLA
├─ ROS2 관련 패키지
├─ Quantized SmolVLA model
└─ smolvla_inference_node.py
```

---

## 7. PyTorch가 Raspberry Pi 5에서 가능한가?

가능하다.

Raspberry Pi 5는 ARM64/aarch64 CPU를 사용하므로 **ARM64용 PyTorch CPU 환경**을 사용할 수 있다.

정상적인 실행 상태는 예를 들어:

```python
import torch

print(torch.__version__)
print(torch.cuda.is_available())
```

결과:

```text
2.x.x
False
```

여기서 `False`는 오류가 아니라 NVIDIA CUDA 없이 **CPU inference를 수행한다는 의미**다.

다만:

```text
실행 가능
≠
충분히 빠른 inference
```

이다.

실제 속도는 Raspberry Pi 5에서 직접 benchmark해야 한다.

따라서 최종적으로:

```text
Original SmolVLA
       ↓
CPU inference baseline
       ↓
INT8 / INT4 quantization
       ↓
모델 경량화
       ↓
Latency / RAM / CPU / 온도 비교
```

순서로 검증하는 것이 좋다.

---

## 8. 현재 가장 먼저 만들어야 하는 것

### Raspberry Pi 5 ARM64용 SmolVLA Docker

검증 순서:

```text
ARM64 Docker
    ↓
Python 실행
    ↓
PyTorch import
    ↓
torchvision
    ↓
LeRobot 설치
    ↓
SmolVLA import
    ↓
SmolVLA checkpoint load
    ↓
Dummy input inference
    ↓
Quantized model inference
    ↓
ROS2 inference node 연결
```

이 Docker가 준비되면 실제 OMY에서는 카메라와 `/joint_states`만 연결하면 된다.

---

# 9. Raspberry Pi가 없을 때 UTM으로 먼저 테스트

현재 실제 Raspberry Pi 5가 없어도 MacBook + UTM을 이용해 상당 부분 미리 개발할 수 있다.

권장 구조:

```text
MacBook M1
└─ UTM
   └─ Ubuntu 24.04 ARM64
      └─ Docker
         └─ smolvla_rpi
            ├─ Python
            ├─ PyTorch ARM64
            ├─ LeRobot
            ├─ SmolVLA
            ├─ Quantized model
            └─ inference code
```

UTM Ubuntu에서 먼저 확인:

```bash
uname -m
```

원하는 결과:

```text
aarch64
```

Docker 내부에서도:

```bash
docker run --rm ubuntu:24.04 uname -m
```

결과:

```text
aarch64
```

이면 ARM64 Docker 호환성 개발 환경으로 사용할 수 있다.

---

## 10. UTM에서 검증 가능한 것

UTM ARM64 환경에서는 다음을 미리 검증할 수 있다.

- ARM64 Docker build
- Python 환경
- PyTorch ARM64 설치
- LeRobot 설치
- SmolVLA import
- checkpoint load
- dummy inference
- 양자화 모델 load
- 양자화 inference
- ROS2 inference node 코드
- Dockerfile 재현성

즉 실제 OMY가 없어도 **소프트웨어 개발은 거의 끝까지 진행 가능**하다.

---

## 11. UTM이 실제 Raspberry Pi 5와 완전히 같은 것은 아님

UTM ARM64 VM은 Raspberry Pi 5 완전 에뮬레이션이 아니다.

같게 맞출 수 있는 부분:

```text
ARM64 / aarch64
Linux
Docker
Python
PyTorch
LeRobot
SmolVLA
ROS2 구조
```

다른 부분:

```text
Mac M1 CPU ≠ Raspberry Pi 5 Cortex-A76
메모리 대역폭
CPU cache
Linux kernel
Pi hardware driver
USB
Camera
GPIO
Serial
발열
실제 inference 성능
```

따라서 UTM의 목적은:

> **Pi 5용 Docker의 소프트웨어 호환성과 코드를 미리 개발·검증하는 것**

이다.

UTM에서 나온 inference latency를 Raspberry Pi 5 성능으로 보면 안 된다.

---

# 12. 전체 개발 순서

## 지금 — MacBook + UTM

```text
UTM ARM64 Ubuntu
       ↓
smolvla_rpi Docker 제작
       ↓
PyTorch ARM64 확인
       ↓
LeRobot 확인
       ↓
SmolVLA load
       ↓
Dummy inference
       ↓
Quantization 적용
       ↓
Quantized inference
       ↓
ROS2 inference node 작성
```

## 이후 — 실제 OMY Raspberry Pi 5

```text
완성된 Docker 배포
       ↓
/joint_states 연결
       ↓
Camera topic 연결
       ↓
Language instruction 입력
       ↓
SmolVLA onboard inference
       ↓
OMY controller 연결
       ↓
실제 Task 수행
       ↓
Latency / RAM / CPU / 온도 측정
```

---

# 최종 구조

```text
                    OMY Raspberry Pi 5

┌────────────────── Cyclo OS ──────────────────┐
│                                               │
│  OMY Bringup                                  │
│      │                                        │
│      └──── /joint_states ───────┐             │
│                                 │             │
│  Camera Node                    │             │
│      │                          │             │
│      └──── /image_raw ──────────┤             │
│                                 ▼             │
│                     ┌────────────────────┐    │
│                     │ smolvla_rpi Docker │    │
│                     │                    │    │
│                     │ PyTorch ARM64 CPU  │    │
│                     │ LeRobot            │    │
│                     │ SmolVLA            │    │
│                     │ Quantized Model    │    │
│                     │                    │    │
│ task instruction ──>│ inference_node     │    │
│                     └─────────┬──────────┘    │
│                               │               │
│                               │ action        │
│                               ▼               │
│                         OMY controller         │
│                               │               │
│                               ▼               │
│                          ros2_control          │
│                               │               │
└───────────────────────────────┼───────────────┘
                                ▼
                               OMY
```

## 핵심 정리

> **현재 가장 먼저 할 일은 MacBook M1의 UTM ARM64 Ubuntu 환경에서 Raspberry Pi 5용 `smolvla_rpi` Docker를 만드는 것이다.**

UTM에서는 Docker/PyTorch/LeRobot/SmolVLA/양자화/ROS2 inference 코드를 미리 검증하고, 이후 실제 OMY Raspberry Pi 5에서는 성능과 하드웨어 연결만 최종 검증한다.
