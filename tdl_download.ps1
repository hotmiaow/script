$url_download = "https://t.me/bjjinstructionalz/"

#tdl.exe download -u  https://t.me/bjjinstructionalz/362

For ($i=271; $i -le 301; $i++) 
{
tdl.exe download -u $url_download$i
Start-Sleep -Seconds 1
}