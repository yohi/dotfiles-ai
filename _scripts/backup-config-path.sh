#!/bin/sh

set -eu

if [ "$#" -lt 1 ] || [ "$#" -gt 2 ]; then
	printf '%s\n' 'Usage: backup-config-path.sh <path> [stamp]' >&2
	exit 2
fi

source_path=$1
if [ ! -e "$source_path" ] && [ ! -L "$source_path" ]; then
	printf 'Backup source does not exist: %s\n' "$source_path" >&2
	exit 1
fi

if [ "$#" -eq 2 ]; then
	stamp=$2
else
	stamp=$(date +%Y%m%d%H%M%S).$$
fi

case $stamp in
	''|*[!A-Za-z0-9._-]*)
		printf '%s\n' 'Backup stamp contains invalid filename characters' >&2
		exit 2
		;;
esac

backup_path="${source_path}.bak.${stamp}"
suffix=0
while [ -e "$backup_path" ] || [ -L "$backup_path" ]; do
	suffix=$((suffix + 1))
	backup_path="${source_path}.bak.${stamp}.${suffix}"
done

mv "$source_path" "$backup_path"
printf '%s\n' "$backup_path"
