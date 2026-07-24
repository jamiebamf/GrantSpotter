document.addEventListener('DOMContentLoaded',()=>{
 const toggle=document.querySelector('.menu-toggle'),sidebar=document.querySelector('.sidebar');
 if(toggle&&sidebar)toggle.addEventListener('click',()=>sidebar.classList.toggle('open'));
 const search=document.getElementById('grantSearch'),filter=document.getElementById('causeFilter'),cards=[...document.querySelectorAll('.match-card')];
 function apply(){const q=(search?.value||'').toLowerCase(),c=filter?.value||'';cards.forEach(card=>{const okQ=!q||card.dataset.title.includes(q),okC=!c||card.dataset.causes.split('|').includes(c);card.style.display=okQ&&okC?'':'none';});}
 search?.addEventListener('input',apply);filter?.addEventListener('change',apply);
});
