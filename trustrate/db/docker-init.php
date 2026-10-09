<?php
// Container layout puts the shared bootstrap in html rather than web.
// Make the same CLI sources work in both local and image layouts.
if(PHP_SAPI!=='cli') exit;
if(!is_dir('/var/www/web')) symlink('/var/www/html','/var/www/web');
require __DIR__.'/init.php';
