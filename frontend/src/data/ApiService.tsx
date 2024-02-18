// import { Cache } from 'aws-amplify/utils';


// function cacheItem(key, value) {
//   Cache.setItem(key, value, { expires: 1800 }); // Expires in 1800 seconds (30 minutes)
// }

// async function retrieveItem(key) {
//   try {
//     const data = await Cache.getItem(key);
//     if (data) {
//       return data;
//     }
//   } catch (e) {
//     console.error('Cache item not found', e);
//     return null;
//   }
// }