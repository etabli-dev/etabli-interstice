# Copyright 2026 R. Heller
# SPDX-License-Identifier: AGPL-3.0-only
"""Read-only CalDAV discovery with explicit credential destination constraints."""
import asyncio
from urllib.parse import urljoin, urlsplit
import httpx
from defusedxml import ElementTree

DAV = '{DAV:}'
CAL = '{urn:ietf:params:xml:ns:caldav}'


def allowed_url(url, hosts):
    parsed = urlsplit(url)
    if parsed.scheme != 'https' or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.port not in (None,443):
        raise ValueError('Invalid calendar discovery URL')
    host = parsed.hostname or ''
    if not any(host == allowed or (allowed.startswith('*.') and host.endswith(allowed[1:])) for allowed in hosts):
        raise ValueError('Discovery destination is not authorized')
    return url


async def discover(url, username, password, allowed_hosts):
    async with asyncio.timeout(90), httpx.AsyncClient(timeout=15, follow_redirects=False, trust_env=False) as client:
        async def propfind(target, properties, depth='0'):
            for _ in range(5):
                allowed_url(target, allowed_hosts)
                body='<d:propfind xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav"><d:prop>'+properties+'</d:prop></d:propfind>'
                async with client.stream('PROPFIND',target,auth=(username,password),
                    headers={'Depth':depth,'Content-Type':'application/xml'},content=body) as response:
                    if response.status_code in (301,302,307,308):
                        target=urljoin(target,response.headers['Location']); continue
                    if response.status_code != 207:
                        raise ValueError('Calendar discovery failed with HTTP '+str(response.status_code))
                    data=bytearray()
                    async for chunk in response.aiter_bytes():
                        data.extend(chunk)
                        if len(data)>2_000_000: raise ValueError('Discovery response too large')
                root=ElementTree.fromstring(data)
                if root.tag != DAV+'multistatus': raise ValueError('Invalid discovery response')
                return target,root
            raise ValueError('Too many discovery redirects')

        target,root=await propfind(url,'<d:current-user-principal/>')
        def href(root, prop):
            for stat in root.findall('.//'+DAV+'propstat'):
                if ' 200 ' in stat.findtext(DAV+'status',''):
                    value=stat.findtext(DAV+'prop/'+prop+'/'+DAV+'href')
                    if value:return value
            raise ValueError('Required discovery property is missing')
        principal=urljoin(target,href(root,DAV+'current-user-principal'))
        target,root=await propfind(principal,'<c:calendar-home-set/>')
        home=urljoin(target,href(root,CAL+'calendar-home-set'))
        target,root=await propfind(home,'<d:resourcetype/><d:displayname/><c:supported-calendar-component-set/>','1')
        collections=[]
        for item in root.findall(DAV+'response'):
            for stat in item.findall(DAV+'propstat'):
                if ' 200 ' not in stat.findtext(DAV+'status',''):continue
                prop=stat.find(DAV+'prop')
                if prop is None or prop.find(DAV+'resourcetype/'+CAL+'calendar') is None:continue
                components=prop.findall(CAL+'supported-calendar-component-set/'+CAL+'comp')
                if components and not any(c.get('name')=='VEVENT' for c in components):continue
                address=allowed_url(urljoin(target,item.findtext(DAV+'href','')),allowed_hosts)
                collections.append({'url':address,'name':prop.findtext(DAV+'displayname','Calendar')})
        if not collections:raise ValueError('No readable event calendars discovered')
        return collections
