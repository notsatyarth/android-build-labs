import zipfile, sys, os
for p in sys.argv[1:]:
    z = zipfile.ZipFile(p)
    dex = [i for i in z.infolist() if i.filename.startswith('classes') and i.filename.endswith('.dex')]
    print(os.path.basename(os.path.dirname(os.path.dirname(p))) if False else p.split('/')[0], p.split('/')[-2], 'apk', os.path.getsize(p), 'dex_files', len(dex), 'dex_bytes', sum(i.file_size for i in dex), 'dex_compressed', sum(i.compress_size for i in dex))
