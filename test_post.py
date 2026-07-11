import requests, re
s = requests.Session()
r = s.get('http://127.0.0.1:5000/')
token = re.search(r'name="csrf_token" value="([^"]+)"', r.text).group(1)
r2 = s.post('http://127.0.0.1:5000/analyze', data={'csrf_token': token, 'input_mode': 'url', 'repo_url': 'https://github.com/google/guava'}, allow_redirects=False)
print('status:', r2.status_code)
if r2.status_code in (301, 302):
    print('location:', r2.headers.get('Location'))
else:
    print('text:', r2.text[:200])
