requireAuth().then((user) => {
  if (user) initTopbar(user);
});
