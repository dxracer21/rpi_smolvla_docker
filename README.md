# smolvla_rpi

Raspberry Pi 5 deployment용 Linux ARM64 컨테이너 개발 환경이다. Mac의 Docker Desktop에서 개발한 동일 이미지를 Raspberry Pi 5의 Docker Engine에서 실행하는 구조이며 Docker-in-Docker가 아니다.

현재 포함된 런타임:

- Ubuntu 24.04 ARM64
- Python 3.12
- PyTorch 2.11.0 CPU-only wheel
- torchvision 0.26.0 CPU-only wheel
- LeRobot 0.6.1 with SmolVLA dependencies

## Base environment verification

```bash
docker compose build
docker compose run --rm smolvla-rpi
```

성공하면 PyTorch CPU wheel 유지 여부와 LeRobot/SmolVLA import 결과 및 `PASS`가 출력된다.

## Development container

```bash
./container.sh start
./container.sh enter
```

컨테이너 관리:

```bash
./container.sh build
./container.sh start
./container.sh enter
./container.sh stop
./container.sh rebuild
```

`container.sh`는 실행 위치와 관계없이 프로젝트의 `compose.yaml`을 사용한다. 컨테이너 이름은 `smolvla-dev`, 이미지 이름은 `smolvla_rpi:dev`로 고정된다.

`stop`은 개발 컨테이너를 중지하고 삭제한다. 이미지와 `models/`의 체크포인트/cache는 삭제하지 않는다.

모델과 Hugging Face cache는 호스트의 `models/`에 저장되며 Git에는 포함되지 않는다.

기본 자원 제한은 Raspberry Pi 5 8GB 모델을 기준으로 CPU 4개, 메모리 8GB, swap 추가 할당 없음이다. 실제 Pi 성능, 발열, 장치 드라이버는 실제 하드웨어에서 별도로 검증해야 한다.

## SmolVLA inference

컨테이너를 시작하고 진입한다.

```bash
./container.sh start
./container.sh enter
```

컨테이너 안에서 로컬 체크포인트로 CPU 더미 인퍼런스를 실행한다.

```bash
python scripts/run_inference.py \
  --model /models/task_20_quant_285000 \
  --task "Pick up the object"
```

290k 체크포인트는 모델 경로만 바꾼다.

```bash
python scripts/run_inference.py \
  --model /models/task_20_quant_290000 \
  --task "Pick up the object"
```

결과를 파일로 남기려면 `--output-json`을 사용한다. `/workspace`는 호스트의 프로젝트 폴더에 마운트되어 있으므로 아래 결과는 컨테이너를 삭제해도 유지된다.

```bash
python scripts/run_inference.py \
  --model /models/task_20_quant_285000 \
  --task "Pick up the object" \
  --output-json /workspace/results/inference_285000.json
```

이 스크립트는 인터넷에서 모델을 내려받지 않는다. 체크포인트와 tokenizer를 지정한 로컬 모델 폴더에서만 읽으며 저장 당시의 CUDA 설정을 CPU로 덮어쓴다. 현재 입력은 실제 카메라와 로봇 상태가 아닌 모델 설정에 맞춰 생성한 테스트 데이터다.
