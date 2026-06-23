#!/usr/bin/env bash
# Provision a Linux admin user for SSH + CLI access (one-time setup).
set -euo pipefail

if [[ $EUID -ne 0 ]]; then
  echo "Must run as root" >&2
  exit 1
fi

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 <username>" >&2
  exit 1
fi

USERNAME="$1"
PASSWORD=$(head -n1)

if [[ -z "${PASSWORD}" ]]; then
  echo "Password required on stdin" >&2
  exit 1
fi

if id "${USERNAME}" &>/dev/null; then
  echo "User ${USERNAME} already exists" >&2
  exit 1
fi

if ! [[ "${USERNAME}" =~ ^[a-z][a-z0-9_-]{2,31}$ ]]; then
  echo "Invalid username" >&2
  exit 1
fi

useradd -m -s /bin/bash "${USERNAME}"
echo "${USERNAME}:${PASSWORD}" | chpasswd
usermod -aG sudo "${USERNAME}"

echo "Provisioned SSH user: ${USERNAME}"
